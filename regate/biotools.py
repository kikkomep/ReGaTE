from __future__ import annotations

import json
import logging
import re

import requests
from urllib.parse import urljoin

from regate.cli.helpers import prompt
from regate.const import _RESOURCE_TYPE
from regate.mapping import find_biotools_regate_id

logger = logging.getLogger()


class BioToolsPlatform(object):
    __instance = None

    @staticmethod
    def getInstance() -> BioToolsPlatform:
        if not BioToolsPlatform.__instance:
            BioToolsPlatform()
        return BioToolsPlatform.__instance

    def __init__(self):
        if BioToolsPlatform.__instance:
            raise Exception("Singleton class: an instance of this class already exists!")
        BioToolsPlatform.__instance = self
        self.__config = None
        self.__token = None

    def configure(self, config) -> None:
        self.__config = config

    @property
    def config(self):
        if not self.__config:
            raise Exception("BioToolsPlatform instance not initialized")
        return self.__config

    @property
    def token(self):
        if not self.__token:
            raise Exception("Authentication required")
        return self.__token

    def authenticate(self, username, password, ssl_verify):
        """
        :param login:
        :return:
        """
        url = self.config.bioregistry_host + '/api/rest-auth/login/'
        resp = requests.post(url, '{{"username": "{0}","password": "{1}"}}'.format(username, password),
                             headers=_build_request_headers(), verify=ssl_verify)
        self.__token = resp.json().get('key')
        return self.__token is not None

    def get_tools(self, filter_list=None, collectionID=None, only_regate_tools=False):
        return self.get_elixir_tools_list(tools_list=filter_list,
                                          tool_type=_RESOURCE_TYPE.TOOL,
                                          tool_collectionID=collectionID,
                                          only_regate_tools=only_regate_tools)

    def get_workflows(self, filter_list=None, collectionID=None, only_regate_tools=False):
        return self.get_elixir_tools_list(tools_list=filter_list,
                                          tool_type=_RESOURCE_TYPE.WORKFLOW,
                                          tool_collectionID=collectionID,
                                          only_regate_tools=only_regate_tools)

    def get_elixir_tools_list(self,
                              tools_list=None, tool_type=_RESOURCE_TYPE.TOOL,
                              tool_collectionID=None, only_regate_tools=False):
        try:
            result = []
            # Prepare tools filter
            tools_list = tools_list.split(',') if tools_list and isinstance(tools_list, str) else tools_list
            tools_filter_ids = [t.lower() for t in tools_list] if tools_list else None
            # Prepare request parameters
            page = 1
            page_pattern = re.compile(r"\?page=(\d+)")
            resource_type = "Web application" if tool_type == _RESOURCE_TYPE.TOOL else "Workflow"
            res_url = urljoin(self.config.bioregistry_host, '/api/tool')
            # load all tools by page
            while page:
                params = {"toolType": resource_type, 'page': page, 'sort': 'name', 'ord': 'asc'}
                if tool_collectionID:
                    params["collectionID"] = tool_collectionID
                resp = requests.get(res_url, headers=_build_request_headers(), params=params)
                if resp.status_code == 200:
                    # filter tools by otherID == biotools:regate_
                    response_json = resp.json()
                    tools = [t for t in response_json["list"] if not only_regate_tools or find_biotools_regate_id(t)]
                    if not tools_list:
                        result.extend(tools)
                    else:
                        for tid in tools_filter_ids:
                            found = False
                            for tool in tools:
                                if tool["biotoolsID"].lower() == tid or tool["name"].lower() == tid:
                                    result.append(tool)
                                    found = True
                                    break
                            if not found:
                                logger.error("Unable to find tool: %s", tid)
                if response_json["next"]:
                    next_page_match = page_pattern.match(response_json["next"])
                    page = next_page_match.group(1) if next_page_match else None
                else:
                    page = None
            return result
        except Exception as e:
            logger.error("Error listing tools from %s", self.config.bioregistry_host)
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)
        return None

    def push_tool(self, data):
        data_as_string = data
        if not isinstance(data, str):
            data_as_string = json.dumps(data)
        url = self.config.bioregistry_host + "/api/tool"
        resp = requests.post(url, data_as_string, headers=_build_request_headers(self.token), verify=self.config.ssl_verify)
        if resp.status_code != 201:
            raise Exception(resp.text)

    def remove_existing_elixir_tool_version(self, tool_id, tool_version, tool_collectionID):
        try:
            # try first with version number
            res_url = urljoin(self.config.bioregistry_host, '/api/tool/{0}/version/{1}'.format(tool_id, tool_version))
            resp = requests.get(res_url, headers=_build_request_headers(self.token))
            if resp.status_code != 200:
                # try without version number
                res_url = urljoin(self.config.bioregistry_host, '/api/tool/{0}'.format(tool_id))
                resp = requests.get(res_url, headers=_build_request_headers(self.token))
            # finally check if a result has been found
            if resp.status_code == 200:
                biotool = resp.json()
                logger.debug('{0} in {1}: {2}'.format(tool_collectionID, biotool.get(
                    'collectionID', []), tool_collectionID in biotool.get('collectionID', [])))
                if tool_collectionID in biotool.get('collectionID', []):
                    logger.debug("removing resource " + tool_id)
                    resp = requests.delete(
                        res_url, headers=_build_request_headers(self.token))
                    if resp.status_code == 204:
                        logger.debug("{0} ok".format(tool_id))
                    else:
                        logger.error("{0} ko, error: {1} {2} (code: {3})".format(tool_id, resp.text, resp.status_code))
        except Exception:
            logger.error("Error removing resource {0}".format(tool_id), exc_info=True)


def _build_request_headers(token=None):
    if token:
        return {'Accept': 'application/json', 'Content-type': 'application/json',
                'Authorization': 'Token {0}'.format(token)}
    return {'Accept': 'application/json', 'Content-type': 'application/json'}
