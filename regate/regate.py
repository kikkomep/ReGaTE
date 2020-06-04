#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Oct. 23, 2014

@author: Olivia Doppelt-Azeroual, CIB-C3BI, Institut Pasteur, Paris
@author: Fabien Mareuil, CIB-C3BI, Institut Pasteur, Paris
@author: Hervé Ménager, CIB-C3BI, Institut Pasteur, Paris
@contact: olivia.doppelt@pasteur.fr
@project: ReGaTE
@githuborganization: C3BI-pasteur-fr
"""

import sys
import re
import os
import json
import copy
import glob
import base64
import shutil
import string
import urllib
import tarfile
import getpass
import logging
import argparse
import requests
import tempfile
import ruamel.yaml
import collections
import configparser
from enum import Enum
import xml.etree.ElementTree as ET
from lxml import etree
from datauri import DataURI
from urllib.parse import urljoin
from Cheetah.Template import Template
from bioblend.galaxy.client import ConnectionError
from bioblend.galaxy import GalaxyInstance as _GalaxyInstance
from logging.handlers import RotatingFileHandler

logger = logging.getLogger()

formatter = logging.Formatter('%(asctime)s :: %(levelname)s :: %(message)s')

# first logger
file_handler = RotatingFileHandler('activity.log', 'a', 1000000, 1)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# second logger
file_handler_edam = RotatingFileHandler('edam_mapping.log', 'a', 1000000, 1)

file_handler_edam.setLevel(logging.WARNING)
file_handler_edam.setFormatter(formatter)
logger.addHandler(file_handler_edam)

REGATE_PREFIX_ID = "biotools:regate"

TOOLSHED_PREFIX_ID = "biotools:toolshed"

REGATE_DATA_FILE = "regate_data_file"

DEFAULT_EDAM_DATA = {
    "term": "Data",
    "uri": "http://edamontology.org/data_0006"
}
DEFAULT_EDAM_FORMAT = {
    "term": "Textual format",
    "uri": "http://edamontology.org/format_2330"
}
DEFAULT_EDAM_OPERATION = {
    "uri": "http://edamontology.org/operation_0004",
    "term": "Operation"
}
DEFAULT_EDAM_TOPIC = {
    "uri": "http://edamontology.org/topic_0003",
    "term": "Topic"
}


class _RESOURCE_TYPE(Enum):
    ALL = "all"
    TOOL = "tool"
    WORKFLOW = "workflow"

    @staticmethod
    def values():
        return [o.value for o in _RESOURCE_TYPE]


class _ALLOWED_SOURCES (Enum):
    GALAXY = "galaxy"
    BIOTOOLS = "biotools"

    @staticmethod
    def values():
        return [o.value for o in _ALLOWED_SOURCES]


class _ALLOWED_COMMANDS (Enum):
    EXPORT = "export"
    PUSH = "push"
    TEMPLATE = "template"

    @staticmethod
    def values():
        return [o.value for o in _ALLOWED_COMMANDS]


# loaded edam mapping dictionary
_EDAM_DICT = None

# reference to the Galaxy instance in use
_GALAXY_INSTANCE = None

#
_ROOT = os.path.abspath(os.path.dirname(__file__))


def get_data_path(path):
    return os.path.join(_ROOT, 'data', path)


class Config(object):

    """
    class config to parse and check the config.ini file
    """

    def __init__(self, configfile, script, options):
        self.conf = load_configuration(configfile)
        self.galaxy_url_api = self.assign("galaxy_server", "galaxy_url_api", ismandatory=True)
        self.api_key = self.assign("galaxy_server", "api_key", ismandatory=True)
        if script == "regate":
            if options.command != _ALLOWED_COMMANDS.TEMPLATE.value:
                if options.platform == _ALLOWED_SOURCES.GALAXY.value or "push" in options:
                    self.galaxy_url = self.assign("galaxy_server", "galaxy_url", ismandatory=True)
                    self.transient_instance = self.assign("galaxy_server", "transient_instance", ismandatory=True, boolean=True)
                    self.tools_default = self.assign("galaxy_server", "tools_default", ismandatory=True)
                    self.contactName = self.assign("galaxy_server", "contactName", ismandatory=True)
                    self.contactUrl = self.assign("galaxy_server", "contactUrl", ismandatory=False)
                    self.contactTel = self.assign("galaxy_server", "contactTel", ismandatory=False)
                    self.contactEmail = self.assign("galaxy_server", "contactEmail", ismandatory=True)
                    self.contactTypeEntity = self.assign("galaxy_server", "contactTypeEntity", ismandatory=True)
                    self.contactTypeRole = self.assign("galaxy_server", "contactTypeRole", ismandatory=True)

                if options.platform == _ALLOWED_SOURCES.BIOTOOLS.value or "push" in options:
                    self.login = self.assign("regate_specific_section", "login", ismandatory=True,
                                             message="login option is mandatory to push resources to Elixir")
                    self.bioregistry_host = self.assign("regate_specific_section", "bioregistry_host", ismandatory=True,
                                                        message="bioregistry_host option is mandatory to export or publish tools and/or workflows to the Elixir registry")
                    self.ssl_verify = self.assign("regate_specific_section", "ssl_verify", ismandatory=True,
                                                  message="ssl_verify option is mandatory to push resources to Elixir", boolean=True)
                    self.accessibility = self.assign("regate_specific_section", "accessibility", ismandatory=True,
                                                     message="accessibility option is mandatory to push resources to Elixir")
                else:
                    self.login = self.assign("regate_specific_section", "login", ismandatory=False)
                    self.bioregistry_host = self.assign("regate_specific_section", "bioregistry_host", ismandatory=False)
                    self.ssl_verify = self.assign("regate_specific_section", "ssl_verify", ismandatory=False, boolean=True)

                self.resourcename = self.assign("galaxy_server", "resourcename", ismandatory=True)
                self.prefix_toolname = self.assign("regate_specific_section", "prefix_toolname", ismandatory=False)
                self.suffix_toolname = self.assign("regate_specific_section", "suffix_toolname", ismandatory=False)
                self.accessibility = self.assign("regate_specific_section", "accessibility", ismandatory=True)
                self.data_uri_prefix = self.assign("regate_specific_section", "data_uri_prefix", ismandatory=True)

            self.tool_dir = self.assign("regate_specific_section", "tool_dir", ismandatory=True)
            self.yaml_file = self.assign("regate_specific_section", "yaml_file", ismandatory=False)
            self.xmltemplate = self.assign("regate_specific_section", "xmltemplate", ismandatory=False)
            self.xsdbiotools = self.assign("regate_specific_section", "xsdbiotools", ismandatory=False)

        if script == "remag":
            self.edam_file = self.assign("remag_specific_section", "edam_file", ismandatory=True)
            self.output_yaml = self.assign("remag_specific_section", "output_yaml", ismandatory=True)

    def assign(self, section, key, ismandatory=True, message=None, boolean=False):
        """
            return value if key exists in config.ini file or an error or None if not, depending on whether the option
            is mandatory or not
        """
        if ismandatory:
            if self.exist(section, key):
                return self.getvalue(section, key, boolean=boolean)
            else:
                if message:
                    raise KeyError(message)
                else:
                    raise KeyError("{0} option is mandatory".format(key))
        if not ismandatory:
            if self.exist(section, key):
                return self.getvalue(section, key, boolean=boolean)
            else:
                return None

    def getvalue(self, section, key, boolean=False):
        """
            test if key is a boolean and return value
        """
        if boolean:
            return self.conf.getboolean(section, key)
        else:
            return self.conf.get(section, key)

    def exist(self, section, key):
        """
            Check if key exist in the section
        """
        if key in self.conf[section] and self.conf.get(section, key):
            return True
        else:
            return False


class GalaxyPlatform(object):

    __instance = None

    @staticmethod
    def getInstance():
        if not GalaxyPlatform.__instance:
            GalaxyPlatform()
        return GalaxyPlatform.__instance

    def __init__(self):
        if GalaxyPlatform.__instance:
            raise Exception("Singleton class: an instance of this class already exists!")
        GalaxyPlatform.__instance = self
        self._galaxy_instance = None

    @property
    def api(self):
        if not self._galaxy_instance:
            raise Exception("Bioblend API not initialized")
        return self._galaxy_instance

    def configure(self, galaxy_url, galaxy_api_key):
        self._galaxy_instance = _GalaxyInstance(galaxy_url, key=galaxy_api_key)
        self._galaxy_instance.verify = False

    def get_tool(self, id):
        try:
            metadata = self.api.tools.show_tool(tool_id=id, io_details=True, link_details=True)
            tool_config = self.get_galaxy_tool_wrapper_config(metadata)
            if tool_config:
                metadata['config'] = tool_config
            return metadata
        except ConnectionError as e:
            if e.status_code == 404:
                logger.warning("Unable to find the tool '%r' on the Galaxy platform @ '%s'", id, self.api.base_url)
            else:
                logger.error("Error during connection with exposed API method for tool {0}".format(str(id)), exc_info=True)
            if logger.level == logging.DEBUG:
                logger.exception(e)
            return None

    def get_tools(self, ids=None, ignore=None):
        tools_metadata = []
        # List of tools to retrieve
        galaxy_tools = None
        if ids:
            galaxy_tools = [{'id': tool_id} for tool_id in ids.split(",")]
        else:
            # Retrieve all available tools in the Galaxy platform
            try:
                galaxy_tools = self.api.tools.get_tools()
                # Ensure the list doesn't contain diplicates checking ID and version
                detect_toolid_duplicate(galaxy_tools)
            except ConnectionError as e:
                raise ConnectionError("Connection with the Galaxy server {0} failed, {1}".format(self.api.base_url, e))

        if galaxy_tools:
            # Set list of tools to be ignored
            ignore_list = ignore.split(',') if ignore else []
            # Load tools details
            for tool in galaxy_tools:
                if not tool['id'] in ignore_list:
                    tool = self.get_tool(tool['id'])
                    if tool:
                        tools_metadata.append(tool)
        return tools_metadata

    def get_galaxy_tool_wrapper_archive(self, tool_id):
        try:
            tool_url = '{}/{}/download'.format(self.api.tools.url, tool_id)
            r = self.api.tools._get(url=tool_url, json=False)
            if r.status_code == 200:
                return r.content
        except Exception as e:
            if logger.level == logging.DEBUG:
                logger.exception(e)
        return None

    def get_galaxy_tool_wrapper_config(self, tool_metadata):
        temp = tempfile.NamedTemporaryFile()
        temp_dir = tempfile.TemporaryDirectory()
        try:
            archive = self.get_galaxy_tool_wrapper_archive(tool_metadata['id'])
            if archive:
                with open(temp.name, "wb") as out:
                    out.write(archive)
                tar_archive = tarfile.open(temp.name, 'r:gz')
                filename_pattern = re.compile(r"^({}|{})\.xml$".format(
                    tool_metadata['id'],
                    tool_metadata['tool_shed_repository']['name']
                    if "tool_shed_repository" in tool_metadata and "name" in tool_metadata['tool_shed_repository']
                    else tool_metadata['name']))
                files = [f for f in tar_archive.getnames()]
                logger.debug("List of files: %r", files)
                if len(files) == 0:
                    logger.debug("No file found on the archive of the galaxy tool wrapper '%s'!", tool_metadata['id'])
                    return None
                elif len(files) > 1:
                    files = [f for f in tar_archive.getnames() if filename_pattern.match(f)]
                    if len(files) == 0 or len(files) > 1:
                        logger.debug("Unable to detect the wrapper config file for tool '%s'", tool_metadata['id'])
                        logger.debug("Files %r (%r)", files, filename_pattern.pattern)
                        return None
                tar_archive.extractall(path=temp_dir.name)
                xml_filename = os.path.join(temp_dir.name, files[0])
                xml_config = ET.parse(xml_filename)
                root = xml_config.getroot()
                return {
                    'command': root.find("command").text,
                    'help': root.find("help").text if root.find("help") else "",
                }
        finally:
            temp.close()
            temp_dir.cleanup()

    def get_workflow(self, workflow_id, export_format=False):
        try:
            workflows = self.api.workflows.get_workflows()
            for wf in workflows:
                if wf['latest_workflow_uuid'] == workflow_id:
                    if wf and export_format:
                        wf = self.api.workflows.export_workflow_dict(wf['id'])
                    return wf
            return None
        except ConnectionError as e:
            logger.error("Error during connection with exposed API method for workflow {0}".format(workflow_id, exc_info=True))
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)
            return None

    def get_workflows(self, ids=None, ignore=None):
        workflows_metadata = []
        # build the list of workflows to export
        galaxy_workflows = None
        if ids:
            galaxy_workflows = [{'id': tool_id} for tool_id in ids.split(",")]
        else:
            # Retrieve all available tools in the Galaxy platform
            try:
                galaxy_workflows = self.api.workflows.get_workflows()
                # Ensure the list doesn't contain diplicates checking ID and version
                # detect_toolid_duplicate(galaxy_workflows)
            except ConnectionError as e:
                raise ConnectionError("Connection with the Galaxy server {0} failed, {1}".format(self.api.base_url, e))
        # Load workdlows details
        if galaxy_workflows:
            # Define list of workflows to be ignored
            ignore_list = ignore.split(',') if ignore else []
            # Load workflow details
            for wf in galaxy_workflows:
                if not wf['id'] in ignore_list:
                    try:
                        metadata = self.api.workflows.export_workflow_dict(wf['id'])
                        workflows_metadata.append(metadata)
                    except ConnectionError as e:
                        logger.error("Error during connection with exposed API method for workflow {0}".format(
                            str(wf['id'])), exc_info=True)
        return workflows_metadata

    def import_workflow(self, workflow_or_filename):
        try:
            data_json = workflow_or_filename
            if isinstance(workflow_or_filename, str) and os.path.isfile(workflow_or_filename):
                with open(workflow_or_filename) as data_file:
                    data_json = json.load(data_file)
            self.api.workflows.import_workflow_dict(data_json, publish=True)
        except ConnectionError as e:
            logger.error("Galaxy import error for workflow in the '%s' JSON file", workflow_or_filename)
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)

    def import_tool(self, tool_or_filename):
        try:
            data_json = tool_or_filename
            if isinstance(tool_or_filename, str):
                with open(tool_or_filename) as data_file:
                    data_json = json.load(data_file)
            if "tool_shed_repository" in data_json:
                toolshed = data_json["tool_shed_repository"]
                self.api.toolShed.install_repository_revision(
                    tool_shed_url="https://{}".format(toolshed["tool_shed"]),
                    name=toolshed["name"],
                    owner=toolshed["owner"],
                    changeset_revision=toolshed["changeset_revision"],
                    install_tool_dependencies=False,
                    install_repository_dependencies=False,
                    install_resolver_dependencies=False,
                    tool_panel_section_id=None,
                    new_tool_panel_section_label=data_json["panel_section_name"]
                )
            else:
                logger.error("Unable to find ToolShed repository info for tool '%s'", data_json["name"])
        except ConnectionError as e:
            logger.error("Galaxy import error for workflow in the '%s' JSON file", tool_or_filename)
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)


def build_tool_name(tool_id, prefix, suffix):
    """
    @tool_id: tool_id
    builds the tool_name with the tool id, its version
    and the prefix/suffix defined in the config file
    """
    try:
        tool_name = str.split(tool_id, '/')[-2]
    except IndexError:
        tool_name = tool_id
    tool_name = re.sub('[^0-9a-zA-Z\_\-\.\~]', '-', tool_name)
    if len(tool_name) > 100:
        tool_name = tool_name[:100]
    if prefix and (len(tool_name) + len(prefix) <= 100):
        tool_name = str(prefix) + '-' + tool_name
    if suffix and (len(tool_name) + len(suffix) <= 100):
        tool_name = tool_name + '-' + str(suffix)
    return tool_name


def get_source_registry(tool_id):
    """
    :param tool_id:
    :return:
    """
    try:
        source_registry = "/".join(tool_id.replace('repos', 'view', 1).split('/')[0:-2])
        return "https://" + source_registry
    except ValueError:
        logger.warning("ValueError:", tool_id)
        return ""


def build_filename(tool_id, version):
    try:
        try:
            source = str.split(tool_id, '/')[-2]
        except IndexError:
            source = tool_id
        return source + "_" + str(version)
    except ValueError:
        logger.warning("ValueError:", tool_id)
        return ""


def format_description(description):
    """
    Test the first and last char of a description and replace them
    with the format adapted to Elixir
    """
    try:
        size = len(description)
        if description[size - 1] == '.':
            return description[0].upper() + description[1:size]
        else:
            return description[0].upper() + description[1:size] + '.'
    except IndexError:
        logger.warning(description)


def detect_toolid_duplicate(tool_list):
    id_list = list()
    for tool in tool_list:
        id_list.append(build_filename(tool['id'], tool['version']))

    duplicate_tools = [item for item, count in list(collections.Counter(id_list).items()) if count > 1]
    if duplicate_tools:
        for dup in duplicate_tools:
            logger.warning("The tool {0} is present multiple times on this instance with the same version.".format(dup))


def edam_to_uri(edam, element):
    """
    :param edam:
    :returns edam uri from an edam term:
    """
    try:
        uri = re.split("_|:", edam)
        if len(uri) == 2:
            uri = "http://edamontology.org/{}_{:0>4d}".format(uri[0], int(uri[1]))
        else:
            uri = "http://edamontology.org/{}_{:0>4d}".format(uri[1], int(uri[2]))
    except TypeError:
        if element == 'data':
            uri = "http://edamontology.org/data_0006"
        else:
            uri = "http://edamontology.org/format_1915"
        logger.warning("EDAM MAPPING: TERM ----{0}---- is missing from EDAM current version".format(edam))
    return uri


def find_edam_format(format_name, mapping_edam):
    """
    :param format_name:
    :param mapping_edam:
    :return: edam format from a format (extension) in galaxy
    """
    if format_name in mapping_edam:
        edam_format = mapping_edam[format_name]['formats'][0]
    else:
        edam_format = DEFAULT_EDAM_FORMAT
    return edam_format


def find_edam_data(format_name, mapping_edam):
    """
    :param format_name:
    :param mapping_edam:
    :return edam data of a defined format_name:
    """
    if format_name in mapping_edam:
        edam_data = mapping_edam[format_name]['data'][0]
    else:
        edam_data = DEFAULT_EDAM_DATA
    return edam_data


def build_tool_description(galaxy_metadata):
    return format_description(galaxy_metadata['description']) if galaxy_metadata['description'] != '' \
        else 'Galaxy tool {0}.'.format(galaxy_metadata['name'])


def build_download_link(config, data, filename="data", mimetype="application/json", charset='utf-8'):
    return "{}?{}".format(
        config.data_uri_prefix,
        urllib.parse.urlencode({
            'filename': filename,
            'data': DataURI.make(mimetype, charset=charset, base64=True, data=data)
        })
    )


def build_biotool_id(conf, galaxy_metadata):
    return build_tool_name(galaxy_metadata['id'], conf.prefix_toolname, conf.suffix_toolname)


def map_tool(galaxy_metadata, conf, edam_mapping):
    """
    Extract informations from a galaxy json tool and return the general json in the biotools format
    :param tool_meta_data: galaxy json tool
    :conf : regate.ini config file
    :return: biotools dictionary
    :rtype: dictionary
    """
    tool_id = build_biotool_id(conf, galaxy_metadata)
    mapping = {
        ##### SUMMARY GROUP #########################################################################################
        'name': build_tool_name(galaxy_metadata['name'], conf.prefix_toolname, conf.suffix_toolname),
        'description': build_tool_description(galaxy_metadata),
        'homepage': "{0}?tool_id={1}".format(urljoin(conf.galaxy_url, '/tool_runner'),
                                             requests.utils.quote(galaxy_metadata['id'])),
        'version': [galaxy_metadata['version']],
        # TODO: check if required or auto filled on registration
        # to obtain an uniq id in galaxy we need the toolshed repository, the owner, the xml toolid, the xml version,
        # if the tool provide from a toolshed, if not we need the xml toolid and the xml version only
        # The easiest : use id of the tool
        'biotoolsID': tool_id,
        'biotoolsCURIE': 'biotools:{}'.format(tool_id),
        'otherID': [
            {
                'type': "biotoolsCURIE",
                'value': "{}_{}".format(REGATE_PREFIX_ID, tool_id),
                'version': galaxy_metadata['version']
            }
        ],

        ##### FUNCTION GROUP ######################################################################################
        'function': build_function_dict(galaxy_metadata, edam_mapping),

        ##### LABELS GROUP ######################################################################################
        'toolType': ["Web application"],
        'topic': galaxy_metadata['edam_topics'] \
        if 'edam_topics' in galaxy_metadata and len(galaxy_metadata['edam_topics']) > 0 \
        else [DEFAULT_EDAM_TOPIC],
        # TODO: check if can be detected from XML configuration file
        'operatingSystem': ['Linux'],
        'language': [],
        'license': '',  # TOD: check whether can be dectected inspecting the web site
        'collectionID': [conf.resourcename],
        'maturity': '',  # Available values: Mature, Emerging, Legacy
        # Avaialbe values: "Free of charge", "Free of charge (with restrictions)", "Commercial"
        'cost': '',
        # Available values: "Open access", "Restricted access",
        'accessibility': [conf.accessibility],
        'ELIXIRPlatform': '',
        'ELIXIRNode': '',

        ##### Link GROUP ######################################################################################
        # Miscellaneous links for the software: e.g., repository, issue tracker, etc.
        # see https://biotools.readthedocs.io/en/latest/curators_guide.html#linktype for the available link types
        'link': [],

        ##### Download GROUP ######################################################################################
        'download': [],

        ##### Documentation GROUP ######################################################################################
        'documentation': [],

        ##### Publication GROUP ######################################################################################
        'publication': [],  # TODO: see how "/citations" works

        ##### Relation GROUP ######################################################################################
        'relation': [],  # TODO: see if it is reasonable to connect tools on platform basis

        ##### Credit GROUP ######################################################################################
        'credit': [
            {
                'name': conf.contactName,
                'email': conf.contactEmail,
                'url': conf.contactUrl,
                'tel': conf.contactTel,
                'typeEntity': conf.contactTypeEntity,
                'typeRole': conf.contactTypeRole.split("."),
                # FIXME: to be completed
                'orcidid': '',
                'gridid': '',
                'note': ''
            }
        ]
    }

    ### Add ToolShedRepository ###
    if 'tool_shed_repository' in galaxy_metadata:
        toolshed = galaxy_metadata['tool_shed_repository']
        mapping['otherID'].extend([
            {
                'type': "biotoolsCURIE",
                'value': "{}_{}_{}_{}_{}".format(TOOLSHED_PREFIX_ID, toolshed['tool_shed'], toolshed['owner'], toolshed['name'], toolshed['name']),
                'version': toolshed['changeset_revision']
            }
        ])

    ##### Download GROUP ######################################################################################
    tool_archive = GalaxyPlatform.getInstance().get_galaxy_tool_wrapper_archive(galaxy_metadata['id'])
    if tool_archive:
        mapping['download'].extend([
            {
                'type': 'Tool wrapper (galaxy)',
                'url': build_download_link(conf, tool_archive,
                                           filename="{}.tar.gz".format(tool_id),
                                           mimetype="application/tar+gzip"),
                'note': "Galaxy Tool tar.gz archive encoded as base64 dataURI on the 'data' URL parameter.",
                'version': galaxy_metadata['version']

            },
            {
                'type': 'Tool wrapper (galaxy)',
                'url': build_download_link(conf, json.dumps(galaxy_metadata),
                                           filename="{}.json".format(galaxy_metadata['id']),
                                           mimetype="application/json"),
                'note': "JSON representation of the Galaxy tool as base64 encoded data URI on the 'data' URL parameter.",
                'version': galaxy_metadata['version']

            }
        ])
    if not conf.transient_instance:
        mapping['download'].extend([
            {
                'type': 'Tool wrapper (galaxy)',
                'url': urljoin(conf.galaxy_url, "{}/{}/{}".format('api/tools/', galaxy_metadata['id'], 'download')),
                'note': "Download {} tool from the Galaxy platform {}".format(galaxy_metadata['name'], conf.galaxy_url),
                'version': galaxy_metadata['version']
            }
        ])

    ##### Link GROUP ######################################################################################
    # Miscellaneous links for the software: e.g., repository, issue tracker, etc.
    # see https://biotools.readthedocs.io/en/latest/curators_guide.html#linktype for the available link types
    if not conf.transient_instance:
        mapping['link'].extend([
            {
                'type': 'Galaxy service',
                'url': urljoin(conf.galaxy_url, galaxy_metadata['link']),
                'note': 'Run the "{}" tool on a Galaxy Platform'.format(galaxy_metadata['id'])
            },
            {
                'type': 'Other',
                'url': urljoin(conf.galaxy_url, "{}/{}?".format('api/tools', galaxy_metadata['id'], 'io_details=true&link_details=true')),
                'note': "Tool metadata available on the Galaxy Platform"
            }
        ])

    result = copy.deepcopy(mapping)
    clean_dict(result)
    return result


def map_workflow_tools(galaxy_metadata, config, mapping_edam):
    tools = {}
    for step_index, step in galaxy_metadata["steps"].items():
        if step['type'] == 'tool':
            galaxy_tool_metadata = GalaxyPlatform.getInstance().get_tool(step['tool_id'])
            if not galaxy_tool_metadata:
                raise Exception("Unable to retrieve metadata of tool '%s'", step['tool_id'])
            tools[step['tool_id']] = map_tool(galaxy_tool_metadata, config, mapping_edam)
    return tools


def map_workflow(galaxy_metadata, conf, mapping_edam):
    """
    Extract informations from a galaxy json tool and return the general json in the biotools format
    :param tool_meta_data: galaxy json tool
    :conf : regate.ini config file
    :return: biotools dictionary
    :rtype: dictionary
    """
    tools = map_workflow_tools(galaxy_metadata, conf, mapping_edam)
    topics = {topic['uri']: topic for t in tools.values() for topic in t['topic']}
    operations = [op for t in tools.values() for op in t['function']]
    name = build_tool_name(galaxy_metadata['name'], conf.prefix_toolname, conf.suffix_toolname)
    mapping = {
        ##### SUMMARY GROUP #########################################################################################
        'name': build_tool_name(name, conf.prefix_toolname, conf.suffix_toolname),
        # FIXME: define a default description if annotation is None
        'description': "workflow description: " + galaxy_metadata['annotation'],
        'homepage': "{}?id={}".format(urljoin(conf.galaxy_url, '/workflow/display_by_id'), galaxy_metadata['uuid']),
        'version': [str(galaxy_metadata['version'])],
        # TODO: check if required or auto filled on registration
        # to obtain an uniq id in galaxy we need the toolshed repository, the owner, the xml toolid, the xml version,
        # if the tool provide from a toolshed, if not we need the xml toolid and the xml version only
        # The easiest : use id of the tool
        'biotoolsID': galaxy_metadata['uuid'],
        'biotoolsCURIE': 'biotools:{}'.format(galaxy_metadata['uuid']),
        'otherID': [
            {
                'type': "biotoolsCURIE",
                'value': "{}_{}".format(REGATE_PREFIX_ID, galaxy_metadata['uuid']),
                'version': galaxy_metadata['version']
            }
        ],

        ##### FUNCTION GROUP ######################################################################################
        'function': operations,

        ##### LABELS GROUP ######################################################################################
        'toolType': ["Workflow"],
        'topic': [t for t in topics.values()],
        # TODO: check if can be detected from XML configuration file
        'operatingSystem': ['Linux'],
        'language': [],
        'license': '',  # TOD: check whether can be dectected inspecting the web site
        'collectionID': [conf.resourcename],
        'maturity': '',  # Available values: Mature, Emerging, Legacy
        # Avaialbe values: "Free of charge", "Free of charge (with restrictions)", "Commercial"
        'cost': '',
        # Available values: "Open access", "Restricted access",
        'accessibility': [conf.accessibility],
        'ELIXIRPlatform': '',
        'ELIXIRNode': '',

        ##### Link GROUP ######################################################################################
        # Miscellaneous links for the software: e.g., repository, issue tracker, etc.
        # see https://biotools.readthedocs.io/en/latest/curators_guide.html#linktype for the available link types
        'link': [],

        ##### Download GROUP ######################################################################################
        'download': [
            {
                'type': 'Tool wrapper (galaxy)',
                'url': build_download_link(conf, json.dumps(galaxy_metadata),
                                           filename="{}.json".format(galaxy_metadata['uuid']),
                                           mimetype="application/json"),
                'note': "Galaxy Workflow definition as base64 encoded data URI on the 'data' URL parameter.",
                'version': galaxy_metadata['version']

            }
        ],

        ##### Documentation GROUP ######################################################################################
        'documentation': [],

        ##### Publication GROUP ######################################################################################
        'publication': [],  # TODO: see how "/citations" works

        ##### Relation GROUP ######################################################################################
        'relation': [],  # TODO: see if it is reasonable to connect tools on platform basis

        ##### Credit GROUP ######################################################################################
        'credit': [
            {
                'name': conf.contactName,
                'email': conf.contactEmail,
                'url': conf.contactUrl,
                'tel': conf.contactTel,
                'typeEntity': conf.contactTypeEntity,
                'typeRole': conf.contactTypeRole.split("."),
                # FIXME: to be completed
                'orcidid': '',
                'gridid': '',
                'note': ''
            }
        ]
    }

    # Miscellaneous links for the software: e.g., repository, issue tracker, etc.
    # see https://biotools.readthedocs.io/en/latest/curators_guide.html#linktype for the available link types
    if not conf.transient_instance:
        mapping['link'].extend([
            {
                'type': 'Galaxy service',
                'url': "{}?id={}".format(urljoin(conf.galaxy_url, '/workflow/display_by_id'), galaxy_metadata['uuid']),
                'note': 'View and run the workflow "{}" on the Galaxy Platform'.format(galaxy_metadata['name'])
            }
        ])

    ##### Download GROUP ######################################################################################
    if not conf.transient_instance:
        mapping['download'].extend([
            {
                'type': 'Tool wrapper (galaxy)',
                'url': urljoin(conf.galaxy_url, "{}/{}/download?format=json-download".format('api/workflows/', galaxy_metadata['uuid'])),
                'note': build_description_note(galaxy_metadata) + "[provided by Galaxy Platform]",  # FIXME: check string
                'version': galaxy_metadata['version']
            }
        ])

    result = copy.deepcopy(mapping)
    clean_dict(result)
    return result


def check_str_data_length(data, length=1000):
    if not data or len(data) == 0:
        return ""
    return "{}...".format(data[:(length-2)]) if len(data) > length else data


def build_description_note(galaxy_metadata):
    return "{} ({})".format(galaxy_metadata["name"], re.sub('^[^a-zA-Z0-9_]+|[^a-zA-Z0-9]+$', '', build_tool_description(galaxy_metadata))) \
        if "description" in galaxy_metadata and galaxy_metadata["description"] \
        else galaxy_metadata["name"]


def build_function_dict(json_tool, mapping_edam):
    """
    Extract information from a galaxy json tool and return a list of functions in the json biotools format
    :param json_tool: galaxy json tool
    :return: list of functions in the json biotools format
    :rtype: list
    """
    list_func = []
    listinps = inputs_extract(json_tool['inputs'], mapping_edam)
    listoutps = outputs_extract(json_tool['outputs'], mapping_edam, listinps)
    if 'edam_operations' in json_tool and len(json_tool['edam_operations']) > 0:
        edam_operation = [{'url': edam_to_uri(o, 'operation')} for o in json_tool['edam_operations']]
    else:
        edam_operation = [DEFAULT_EDAM_OPERATION]
    logger.debug("EDAM operation: %r -- %r -- %r", edam_operation, DEFAULT_EDAM_OPERATION, json_tool['edam_operations'])
    cmd = ""
    note = build_description_note(json_tool)
    if 'config' in json_tool and json_tool['config']:
        cmd = json_tool['config']['command'] if 'command' in json_tool['config'] else ""
    func_dict = {
        'operation': [DEFAULT_EDAM_OPERATION],
        'output': listoutps,
        'input': listinps,
        'cmd': check_str_data_length(cmd),
        'note': note,
    }
    list_func.append(func_dict)
    return list_func


def inputs_extract(inputs_json, mapping_edam):
    """
    Extract type data param of a galaxy json tool inputs and return a list of dictionary in the json biotools format
    :param inputs_json: inputs part of a json tool
    :return: list of dictionary in the json biotools format
    :rtype: list
    """

    def inputs_extract_data(data_json):
        """
        Save param type data from a json tool galaxy in a list
        :param data_json:
        :return: None
        """
        data_types = None
        data_formats = None
        if "edam" in data_json and "edam_formats" in data_json["edam"]:
            data_formats = [{'uri': edam_to_uri(f, 'format')} for f in data_json["edam"]["edam_formats"]]
        else:
            data_formats = [find_edam_format(extension, mapping_edam) for extension in data_json["extensions"]]
        if "edam" in data_json and "edam_data" in data_json["edam"]:
            data_types = [{'uri': edam_to_uri(d, 'data')} for d in data_json["edam"]["edam_data"]]
        else:
            data_types = [find_edam_data(extension, mapping_edam) for extension in data_json["extensions"]]

        if len(data_types) == 1:
            data_item = {
                'data': data_types[0],
                'format': data_formats,
                'dataHandle': data_json['name'],
                'dataDescription': data_json['label']
            }
        else:
            data_item = {
                'data': DEFAULT_EDAM_DATA,
                'format': data_formats,
                'dataHandle': data_json['name'],
                'dataDescription': data_json['label']
            }
        listdata.append(data_item)

    def inputs_extract_repeat(repeat_json):
        """
        Recursive function in order to explore repeat param of a galaxy json tool
        :param repeat_json: Repeat param part of a galaxy json tool
        :return: None
        """
        for dictinprep in repeat_json['inputs']:
            if dictinprep['type'] == "conditional":
                inputs_extract_conditional(dictinprep)
            elif dictinprep['type'] == "repeat":
                inputs_extract_repeat(dictinprep)
            elif dictinprep["type"] in ["data", "datacollection"]:
                inputs_extract_data(dictinprep)

    def inputs_extract_conditional(conditional_json):
        """
        Recursive function in order to explore conditional param of a galaxy json tool
        :param conditional_json: conditional param part of a galaxy json tool
        :return: None
        """
        for case in conditional_json["cases"]:
            for dictinpcond in case["inputs"]:
                if dictinpcond['type'] == "conditional":
                    inputs_extract_conditional(dictinpcond)
                elif dictinpcond['type'] == "repeat":
                    inputs_extract_repeat(dictinpcond)
                elif dictinpcond["type"] in ["data", "datacollection"]:
                    inputs_extract_data(dictinpcond)

    listdata = list()
    for dictinp in inputs_json:
        if dictinp['type'] == "conditional":
            inputs_extract_conditional(dictinp)
        elif dictinp['type'] == "repeat":
            inputs_extract_repeat(dictinp)
        elif dictinp["type"] in ["data", "datacollection"]:
            inputs_extract_data(dictinp)
    # if any([len(data['dataType'])==0 or len(data['dataFormat'])==0 for data in listdata]):
    #    logger.warning("data/formats mapping not found for inputs_json:" + str(inputs_json))
    return listdata


def outputs_extract(outputs_json, mapping_edam, biotools_inputs):
    """
    Extract type output param of a galaxy json tool outputs and return a list of dictionary in the json biotools format
    :param outputs_json: output param of a galaxy json tool outputs
    :return: list of dictionary in the json biotools format
    :rtype: dictionary
    """
    listoutput = list()
    for output in outputs_json:
        if output['format'] != 'input':
            try:
                edam_data = {'uri': edam_to_uri(output["edam_data"], 'data')} \
                    if "edam_data" in output else find_edam_data(output['format'], mapping_edam)
                edam_format = {'uri': edam_to_uri(output["edam_format"], 'format')} \
                    if "edam_format" in output else find_edam_format(output['format'], mapping_edam)
                outputdict = {
                    'data': edam_data,
                    'format': [edam_format],
                    'dataHandle': output['format'], 'dataDescription': output['name']
                }
            except KeyError:
                logger.warning(
                    "EDAM MAPPING: TERM ----{0}---- is missing from EDAM current version".format(output['format']))
        else:
            # FIXME: copying the datatype/format from the source would work if only the Galaxy API used
            # by bioblend sent the format_source information
            # biotools_input_source = [biotools_input for biotools_input in biotools_inputs if biotools_input['dataHandle']==output['format_source']][0]
            # outputdict = {'dataType': biotools_input_source['dataType'],
            #         'dataFormat': biotools_input_source['dataFormat'],
            #         'dataHandle': output['format'], 'dataDescription': output['name']
            #          }
            outputdict = {'data': DEFAULT_EDAM_DATA,
                          'format': [DEFAULT_EDAM_FORMAT],
                          'dataHandle': output['format'], 'dataDescription': output['name']
                          }
        listoutput.append(outputdict)
    return listoutput


# def extract_edam_from_galaxy(mapping_edam=None):
#    """
#    :param mapping_edam:
#    :return:
#    """
#    if not mapping_edam:
#        mapping_edam = {}
#    return mapping_edam


def build_edam_dict(yaml_file):
    """
    :param yaml_file:
    :return:
    """
    # map_edam = extract_edam_from_galaxy()
    with open(yaml_file, "r") as file_edam:
        map_edam = ruamel.yaml.load(file_edam, Loader=ruamel.yaml.Loader)
        for key, value in map_edam.items():
            for term in value['formats']:
                term['uri'] = edam_to_uri(term['uri'], 'format')
            for term in value['data']:
                term['uri'] = edam_to_uri(term['uri'], 'data')
    return map_edam


def _build_request_headers(token=None):
    if token:
        return {'Accept': 'application/json', 'Content-type': 'application/json',
                'Authorization': 'Token {0}'.format(token)}
    return {'Accept': 'application/json', 'Content-type': 'application/json'}


def auth(login, host, ssl_verify):
    """
    :param login:
    :return:
    """
    key = None
    while key is None:
        password = getpass.getpass(prompt="  => password: ")
        url = host + '/api/rest-auth/login/'
        resp = requests.post(url, '{{"username": "{0}","password": "{1}"}}'.format(login, password),
                             headers=_build_request_headers(), verify=ssl_verify)
        key = resp.json().get('key')
    return key


def remove_existing_elixir_tool_version(registry_url, token, tool_id, tool_version, tool_collectionID):
    try:
        # try first with version number
        res_url = urljoin(registry_url, '/api/tool/{0}/version/{1}'.format(tool_id, tool_version))
        resp = requests.get(res_url, headers=_build_request_headers(token))
        if resp.status_code != 200:
            # try without version number
            res_url = urljoin(registry_url, '/api/tool/{0}'.format(tool_id))
            resp = requests.get(res_url, headers=_build_request_headers(token))
        # finally check if a result has been found
        if resp.status_code == 200:
            biotool = resp.json()
            logger.debug('{0} in {1}: {2}'.format(tool_collectionID, biotool.get(
                'collectionID', []), tool_collectionID in biotool.get('collectionID', [])))
            if tool_collectionID in biotool.get('collectionID', []):
                logger.debug("removing resource " + tool_id)
                resp = requests.delete(
                    res_url, headers=_build_request_headers(token))
                if resp.status_code == 204:
                    logger.debug("{0} ok".format(tool_id))
                else:
                    logger.error("{0} ko, error: {1} {2} (code: {3})".format(tool_id, resp.text, resp.status_code))
    except Exception:
        logger.error("Error removing resource {0}".format(tool_id), exc_info=True)


def push_to_elix(login, host, ssl_verify, biotools_json_files, resourcename, xsd=None):
    """
    :param login:
    :param tool_dir:
    :return:
    """
    ok_cnt = 0
    ko_cnt = 0

    # Get Auth Token
    print("\n> Provide password for the BioTools user '%s'" % login)
    logger.debug("authenticating...")
    token = auth(login, host, ssl_verify)
    logger.debug("authentication ok")

    print("\n> Importing tools/workflows into the BioTools platform...")

    # POST BioTool JSON files
    for jsonfile in biotools_json_files:
        json_string = open(jsonfile, 'r').read()
        json_data = json.loads(json_string)
        print("  - Importing {} (id.{}, vers.{})... ".format(json_data['name'], json_data['biotoolsID'], json_data['version'][0]), end='', flush=True)
        # TODO: replace removal with a proper upgrade
        remove_existing_elixir_tool_version(host, token, json_data['biotoolsID'], json_data['version'][0], resourcename)
        url = host + "/api/tool"
        resp = requests.post(url, json_string, headers=_build_request_headers(token), verify=ssl_verify)
        if resp.status_code == 201:
            logger.debug("{0} ok".format(os.path.basename(jsonfile)))
            ok_cnt += 1
            print("DONE")
        else:
            logger.error("{0} ko, error: {1}".format(os.path.basename(jsonfile), resp.text))
            ko_cnt += 1
            print("ERROR")
#    if xsd:
#        xsdparse = etree.parse(xsd)
#    else:
#        xsdparse = etree.parse(os.path.join('$PREFIXDATA', 'biotools.xsd'))
#    schema = etree.XMLSchema(xsdparse)
#    parser = etree.XMLParser(schema = schema)
#    for xmlfile in glob.glob(os.path.join(tool_dir, "*.xml")):
#        try:
#            xmltree = etree.parse(xmlfile, parser)
#        except etree.XMLSyntaxError, err:
# print  "XML {0} is wrong formated, {1}".format(os.path.basename(xmlfile), err)
#            continue
#        url = host+"/api/tool"
#        resp = requests.post(url, etree.tostring(xmltree, pretty_print=True),
#                             headers={'Accept': 'application/json', 'Content-type': 'application/xml',
#                                      'Authorization': 'Token {0}'.format(token)}, verify=ssl_verify)
#        if resp.status_code == 201:
#            print "{0} ok".format(os.path.basename(xmlfile))
#            ok_cnt += 1
#        else:
#            print "{0} ko, error: {1}".format(os.path.basename(xmlfile), resp.text)
#            ko_cnt += 1
    logger.info("import finished, ok={0}, ko={1}".format(ok_cnt, ko_cnt))


def clean_list(jsonlist):
    """
    :param jsonlist:
    :return:
    """
    nullindexlist = []
    for elem in range(len(jsonlist)):
        if isinstance(jsonlist[elem], dict):
            clean_dict(jsonlist[elem])
        if isinstance(jsonlist[elem], list):
            clean_list(jsonlist[elem])
        if len(jsonlist[elem]) == 0:
            nullindexlist.append(elem)
    if nullindexlist:
        nullindexlist.sort(reverse=True)
        for i in nullindexlist:
            jsonlist.pop(i)
    return


def clean_dict(jsondict):
    """
    :param jsondict:
    :return:
    """
    for sonkey, sonvalue in list(jsondict.items()):
        if sonvalue:
            if isinstance(sonvalue, dict):
                clean_dict(sonvalue)
            if isinstance(sonvalue, list):
                clean_list(sonvalue)

        if not sonvalue:
            del jsondict[sonkey]
    return


def write_json_files(tool_name, general_dict, tool_dir):
    """
    :param tool_name:
    :param general_dict:
    :return:
    """
    with open(os.path.join(tool_dir, tool_name + ".json"), 'w') as tool_file:
        json.dump(general_dict, tool_file, indent=4)


def write_xml_files(tool_name, general_dict, tool_dir, xmltemplate=None):
    """
    :param tool_name:
    :param general_dict:
    :return:
    """
    if xmltemplate:
        template_path = xmltemplate
    else:
        template_path = get_data_path('xmltemplate.tmpl')

    with open(os.path.join(tool_dir, tool_name + ".xml"), 'w') as tool_file:
        template = Template(file=template_path, searchList=[general_dict])
        tool_file.write(str(template))


def get_resource_folder(conf, platform, type):
    base_dir = conf.tool_dir
    return "{}{}".format(os.path.join(base_dir, platform, type), 's')


def build_biotools_files(conf, type, galaxy_metadata):
    """
    :param tools_metadata:
    :return:
    """
    # setup tools paths
    tools_dir = get_resource_folder(conf, "biotools", type)
    if not os.path.exists(tools_dir):
        os.makedirs(tools_dir)

    # load edam mapping
    mapping_edam = load_edam_dict(conf)

    # write tools
    mappings = []
    print("> Converting {}s into the BioTools format...".format(type))
    for metadata in galaxy_metadata:
        try:
            print("   - {} {} (id.{}, ver.{})...".format(type, metadata["name"], metadata['id' if type == "tool" else "uuid"], metadata["version"]), end='', flush=True)
            biotools_metadata = map_tool(metadata, conf, mapping_edam) if type == "tool" else map_workflow(metadata, conf, mapping_edam)
            file_name = build_filename(metadata['id' if type == "tool" else "uuid"], metadata['version'])
            write_json_files(file_name, biotools_metadata, tools_dir)
            with open(os.path.join(tools_dir, "{}.yaml".format(file_name)), 'w') as outfile:
                ruamel.yaml.safe_dump(biotools_metadata, outfile)
            mappings.append(biotools_metadata)
            print("DONE")
        except Exception as e:
            print("ERROR")
            if logger.level == logging.DEBUG:
                logger.exception(e)
    return mappings


def generate_template(filename="regate.ini"):
    """
    :return:
    """
    if os.path.exists(filename):
        raise FileExistsError("Filename '%s' already exists!", filename)
    template_config = get_data_path('regate.ini')
    with open(template_config, 'r') as configtemplate:
        with open(filename, 'w') as fp:
            for line in configtemplate:
                fp.write(line)


def load_configuration(configfile):
    """
    :param configfile:
    :return:
    """
    configuration = configparser.ConfigParser()
    configuration.read(configfile)
    return configuration


def load_config(options):
    if not os.path.exists(options.config_file):
        raise IOError("{0} doesn't exist".format(options.config_file))
    config = Config(options.config_file, "regate", options)
    logger.debug("Configuration file: %r", config)
    return config


def load_edam_dict(config):
    # if not EDAM_DICT:
    if config.yaml_file:
        EDAM_DICT = build_edam_dict(config.yaml_file)
    else:
        EDAM_DICT = build_edam_dict(get_data_path('yaml_mapping.yaml'))
    return EDAM_DICT


def export_galaxy_tools(config, tools_filter=None):
    print("\nConverting Galaxy tools into a BioTools format...")
    print("> Loading list of Galaxy tools... ", end='', flush=True)
    # Build the list of tools to export
    galaxy_metadata = GalaxyPlatform.getInstance().get_tools(ids=tools_filter, ignore=config.tools_default)
    print("DONE")
    # Generate BioTools files for both tools
    biotools_metadata = build_biotools_files(config, type="tool", galaxy_metadata=galaxy_metadata)
    return biotools_metadata


def export_galaxy_workflows(config, workflows_filter=None):
    print("\nConverting Galaxy workflows into a BioTools format...")
    print("> Loading list of Galaxy workflows... ", end='', flush=True)
    # exported workflows
    # TODO: add ignore list for workflows, ignore=config.tools_default)
    workflows_metadata = GalaxyPlatform.getInstance().get_workflows(ids=workflows_filter)
    print("DONE")
    # Generate BioTools files for both tools and workflows
    biotools_metadata = build_biotools_files(config, type="workflow", galaxy_metadata=workflows_metadata)
    return biotools_metadata


def export_from_galaxy(options):
    # Load configuration file
    config = load_config(options)
    # configure the Galaxy instance
    GalaxyPlatform.getInstance().configure(config.galaxy_url, config.api_key)
    # Export tools
    tools = []
    if options.resource == "tools" or options.resource == "all":
        tools.extend(export_galaxy_tools(config, options.filter if "filter" in options else None))
    # Export workflows
    workflows = []
    if options.resource == "workflows" or options.resource == "all":
        workflows.extend(export_galaxy_workflows(config, options.filter if "filter" in options else None))
    # Publish tool/workflows
    if options.publish:
        # Build list of BioTools JSON files to publish
        biotools_json_files = []
        biotools = tools.copy()
        biotools.extend(workflows)
        # collect biotools files
        for biotool in biotools:
            tools_dir = get_resource_folder(config,
                                            _ALLOWED_SOURCES.BIOTOOLS.value,
                                            "workflow" if biotool["toolType"][0] == "Workflow" else "tool")
            filename = os.path.join(tools_dir, "{}.json".format(build_filename(biotool['biotoolsID'], biotool['version'][0])))
            if os.path.exists(filename):
                biotools_json_files.append(filename)
        # Publish BioTools files
        if len(biotools_json_files) == 0:
            print("No file to publish on the ELIXIR registry '{}'".format(config.bioregistry_host))
        else:
            push_to_elix(config.login, config.bioregistry_host, config.ssl_verify, biotools_json_files, config.resourcename)


def find_biotools_regate_id(tool):
    if tool:
        for oid in tool["otherID"]:
            if oid["value"].startswith(REGATE_PREFIX_ID):
                return oid
    return None


def find_biotools_toolshed_id(tool):
    toolshed_id = None
    for oid in tool["otherID"]:
        if oid["value"].startswith(TOOLSHED_PREFIX_ID):
            tid_parts = oid["value"].split("_")
            toolshed_id = {
                "tool_shed": tid_parts[1],
                "owner": tid_parts[2],
                "name": tid_parts[3],
                "changeset_revision": oid["version"],
            }
    return toolshed_id


def get_elixir_tools_list(registry_url, tools_list=None, tool_type=_RESOURCE_TYPE.TOOL,  tool_collectionID=None, only_regate_tools=False):
    try:
        resource_type = "Web application" if tool_type == _RESOURCE_TYPE.TOOL else "Workflow"
        res_url = urljoin(registry_url, '/api/tool')
        params = {"toolType": resource_type}
        if tool_collectionID:
            params["collectionID"] = tool_collectionID
        resp = requests.get(res_url, headers=_build_request_headers(), params=params)
        if resp.status_code == 200:
            # filter tools by otherID == biotools:regate_
            tools = [t for t in resp.json()["list"] if not only_regate_tools or find_biotools_regate_id(t)]
            tools_list = tools_list.split(',') if tools_list and isinstance(tools_list, str) else tools_list
            if tools_list:
                filtered_tools = []
                tools_id = [t.lower() for t in tools_list]
                for tid in tools_id:
                    found = False
                    for tool in tools:
                        if tool["biotoolsID"].lower() == tid or tool["name"].lower() == tid:
                            filtered_tools.append(tool)
                            found = True
                            break
                    if not found:
                        logger.error("Unable to find tool: %s", tid)
                return filtered_tools
            return tools
    except Exception as e:
        logger.error("Error listing tools from %s", registry_url)
        if logger.isEnabledFor(logging.DEBUG):
            logger.exception(e)
    return None


# def push_to_galaxy(config, galaxy_json_files):
#     # configure the Galaxy instance
#     gi = GalaxyPlatform.getInstance()
#     gi.configure(config.galaxy_url, config.api_key)
#     # setup tools paths
#     for galaxy_json_file in galaxy_json_files:
#         try:
#             with open(galaxy_json_file) as f:
#                 resource = json.load(f)
#                 if resource.get('model_class', False) == "StoredWorkflow" \
#                     or resource.get("a_galaxy_workflow", False) == "true":
#                     gi.import_workflow(galaxy_json_file)
#                 elif resource.get('model_class', False) == "Tool":
#                     pass
#         except Exception as e:
#             logger.error("Galaxy import error for tool in the '%s' JSON file", galaxy_json_file)
#             if logger.isEnabledFor(logging.DEBUG):
#                 logger.exception(e)


def decode_datafile_from_datauri(link, output_folder, write_datafile=True):
    unuri = urllib.parse.urlparse(link)
    qparams = urllib.parse.parse_qs(unuri.query)
    filename = qparams['filename'][0]
    dataURI = qparams['data'][0]
    header, encoded = dataURI.split(",", 1)
    data = base64.b64decode(encoded).decode('utf-8')
    datafile = os.path.join(output_folder, filename)
    if write_datafile:
        with open(datafile, "w") as out:
            out.write(data)
    return datafile


def push_to_galaxy(config, galaxy_json_files, check_exists=True):
    print("\nPublishing exported tools/workflows to Galaxy...")
    print("> Loading Galaxy info... ")
    # Init Galaxy
    gi = GalaxyPlatform.getInstance()
    gi.configure(config.galaxy_url, config.api_key)
    # Load Galaxy tools
    # TODO: can we optimize this step ???
    print("   - Galaxy tools... ", end='', flush=True)
    tools = gi.get_tools() if check_exists else False
    print("DONE")
    # Load Galaxy workflows
    # TODO: can we optimize this step ???
    print("   - Galaxy workflows... ", end='', flush=True)
    workflows = gi.get_workflows() if check_exists else False
    print("DONE")
    # Import all tools/workflows
    print("> Importing tools into the Galaxy platform...")
    for galaxy_json_file in galaxy_json_files:
        with open(galaxy_json_file) as f:
            resource = json.load(f)
            print("  - Importing {} (vers.{})... ".format(resource["name"], resource["version"]), end='', flush=True)
            if resource.get('model_class', False) == "StoredWorkflow" \
                    or resource.get("a_galaxy_workflow", False) == "true":
                if check_exists and \
                    len([w for w in workflows
                            if w['name'] == resource['name'] and
                            w['version'] == resource['version']]) > 0:
                    logger.info("Workflow %s [ver. %s] already exists", resource['name'], resource['version'])
                    print("EXISTS")
                    continue
                gi.import_workflow(galaxy_json_file)
                print("DONE")
            elif resource.get('model_class', False) == "Tool":
                if check_exists and \
                    len([t for t in tools
                            if t['name'] == resource['name'] and
                            t['version'] == resource['version']]) > 0:
                    logger.info("Tool %s [ver. %s] already exists", resource['name'], resource['version'])
                    print("EXISTS")
                    continue
                gi.import_tool(galaxy_json_file)
                print("DONE")


def export_biotools_tools(config, tools_filter=None):
    print("\nConverting Biotools tools into a Galaxy format...")
    # NOTE: the 'only_regate_tools' constraint might be relaxed
    print("> Loading list of BioTools tools... ", end='')
    biotools = get_elixir_tools_list(config.bioregistry_host,
                                     tools_list=tools_filter.split(',') if tools_filter else None,
                                     tool_type=_RESOURCE_TYPE.TOOL, only_regate_tools=True)
    print("DONE")
    # init output folder
    output_folder = get_resource_folder(config, _ALLOWED_SOURCES.GALAXY.value, "tool")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    print("> Converting tools:")
    success = []
    failure = []
    for tool in biotools:
        print("   - tool {}...".format(tool["biotoolsID"]), end='')
        toolshed_info = find_biotools_toolshed_id(tool)
        if toolshed_info:
            data_json = {
                "id": tool["biotoolsID"],
                "model_class": "Tool",
                "name": tool["name"],
                "version": tool["version"][0],
                "panel_section_name": config.resourcename,
                "tool_shed_repository": toolshed_info,
            }
            data_file = os.path.join(output_folder, "{}.json".format(tool["biotoolsID"]))
            try:
                with open(data_file, "w") as out:
                    out.write(json.dumps(data_json, indent=2))
                    tool[REGATE_DATA_FILE] = data_file
                success.append(tool)
                print("DONE")
            except Exception as e:
                print("ERROR")
                failure.append(tool)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.exception(e)            
        else:
            tool_folder = os.path_join(output_folder, "not_imported", tool["name"])
            os.makedirs(tool_folder, exist_ok=True)
            try:
                links = [link["url"] for link in tool["download"]
                         if link["url"].startswith(config.data_uri_prefix)]
                if len(links) == 0:
                    raise Exception("No DataURI link found")
                elif len(links) > 1:
                    raise Exception("More than one DataURI link found. We support one version only")
                for link in links:
                    workflow[REGATE_DATA_FILE] = decode_datafile_from_datauri(link, output_folder=tool_folder, write_datafile=True)
                success.append(tool)
                print("DONE")
            except Exception as e:
                print("ERROR")
                failure.append(tool)
                logger.error("Unable to extract Galaxy workflow definition from BioTools")
                if logger.isEnabledFor(logging.DEBUG):
                    logger.exception(e)
    return success, failure


def export_biotools_workflows(config, workflows_filter=None):
    print("\nConverting Biotools workflows into a Galaxy format...")
    # NOTE: the 'only_regate_tools' constraint might be relaxed
    print("> Loading list of BioTools workflows... ", end='', flush=True)
    workflows = get_elixir_tools_list(config.bioregistry_host,
                                      tools_list=workflows_filter.split(',') if workflows_filter else None,
                                      tool_type=_RESOURCE_TYPE.WORKFLOW,
                                      tool_collectionID=None, only_regate_tools=True)
    print("DONE")
    # init output folder
    output_folder = get_resource_folder(config, _ALLOWED_SOURCES.GALAXY.value, "workflow")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    print("> Converting workflows:")
    success = []
    failure = []
    for workflow in workflows:
        try:
            print("   - workflow {} (id.{}, ver.{})...".format(workflow["name"], workflow["biotoolsID"], workflow["version"][0]), end='')
            links = [link["url"] for link in workflow["download"]
                     if link["url"].startswith(config.data_uri_prefix)]
            if len(links) == 0:
                raise Exception("No DataURI link found")
            elif len(links) > 1:
                raise Exception("More than one DataURI link found. We support one version only")
            for link in links:
                workflow[REGATE_DATA_FILE] = decode_datafile_from_datauri(link, output_folder=output_folder, write_datafile=True)
            success.append(workflow)
            print("DONE")
        except Exception as e:
            print("ERROR")
            failure.append(workflow)
            logger.error("Unable to extract Galaxy workflow definition from BioTools")
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception(e)
    return success, failure


def export_from_biotools(options):
    # Load configuration file
    config = load_config(options)
    # Export tools
    tools = []
    tools_failures = None
    if options.resource == "tools" or options.resource == "all":
        tok, tools_failures = export_biotools_tools(config, options.filter if "filter" in options else None)
        tools.extend(tok)
    # Export workflows
    workflows = []
    workflows_failures = None
    if options.resource == "workflows" or options.resource == "all":
        wok, workflows_failures = export_biotools_workflows(config, options.filter if "filter" in options else None)
        workflows.extend(wok)
    # Publish tool/workflows
    if options.push:
        # Build list of BioTools JSON files to publish
        galaxy_json_files = [resource[REGATE_DATA_FILE] for resource in tools] + \
                            [resource[REGATE_DATA_FILE] for resource in workflows]
        push_to_galaxy(config, galaxy_json_files, check_exists=True)


def export(args):
    logger.debug("cmd: %s", args.command)
    if args.platform == "galaxy":
        export_from_galaxy(args)
    elif args.platform == "biotools":
        export_from_biotools(args)
    else:
        raise Exception("Unsupported platform ''")


def publish_to_bioblend(options):
    # Build list of BioTools JSON files to publish
    biotools_json_files = []

    # Load configuration file
    config = load_config(options)

    tools_dir = get_resource_folder(config, _ALLOWED_SOURCES.BIOTOOLS.value, "tool")
    if options.resource == "all" or options.resource == "tools":
        biotools_json_files.extend([f for f in glob.glob(os.path.join(tools_dir, "*.json")) if os.path.isfile(f)])

    workflows_dir = get_resource_folder(config, _ALLOWED_SOURCES.BIOTOOLS.value, "workflow")
    if options.resource == "all" or options.resource == "workflows":
        biotools_json_files.extend([f for f in glob.glob(os.path.join(workflows_dir, "*.json")) if os.path.isfile(f)])

    if len(biotools_json_files) == 0:
        print("No file to publish on the ELIXIR registry '{}'".format(config.bioregistry_host))
    else:
        push_to_elix(config.login, config.bioregistry_host, config.ssl_verify, biotools_json_files, config.resourcename)


def publish_to_galaxy(options):
    # Build list of BioTools JSON files to publish
    galaxy_json_files = []

    # Load configuration file
    config = load_config(options)

    tools_dir = get_resource_folder(config, _ALLOWED_SOURCES.GALAXY.value, "tool")
    if options.resource == "all" or options.resource == "tools":
        galaxy_json_files.extend([f for f in glob.glob(os.path.join(tools_dir, "*.json")) if os.path.isfile(f)])

    workflows_dir = get_resource_folder(config, _ALLOWED_SOURCES.GALAXY.value, "workflow")
    if options.resource == "all" or options.resource == "workflows":
        galaxy_json_files.extend([f for f in glob.glob(os.path.join(workflows_dir, "*.json")) if os.path.isfile(f)])

    push_to_galaxy(config, galaxy_json_files, check_exists=True)


def push(args):
    logger.debug("cmd: %s", args.command)
    if args.platform == "biotools":
        push_to_target_platform(args)
    elif args.platform == "galaxy":
        push_to_target_platform(args)
    else:
        logger.error("Unsupported target platform '%s'", args.platform)


def template(args):
    logger.debug("cmd: %s", args.command)
    generate_template(args.filename)


def build_cli_parser():
    parser = argparse.ArgumentParser(description="Bridging Tool for Galaxy and BioTools Registry",
                                     formatter_class=lambda prog: argparse.HelpFormatter(prog, width=140, max_help_position=100))

    parser.add_argument("--debug", action="store_true", help="Enable DEBUG level")
    parser.add_argument("--config_file",
                        help="configuration file for regate or remag",
                        default="regate.ini")

    sp = parser.add_subparsers(title='available commands')

    # template command
    template_parser = sp.add_parser("template", help="generate a template for the 'regate.ini' configuration file")
    template_parser.set_defaults(command='template')
    template_parser.add_argument("-f", "--file", dest="filename", default="regate.ini",
                                 help="configuration filename for regate or remag (default 'regate.ini')")

    # export command
    export_parser = sp.add_parser("export",
                                  help="export (and optionally publish) tools and/or workflows ",
                                  formatter_class=lambda prog: argparse.HelpFormatter(prog, width=140, max_help_position=100))
    export_parser.add_argument("--from", dest="platform", choices=[o.value for o in _ALLOWED_SOURCES],
                               required=True,
                               help="source platform for exporting tools and/or workflows")
    export_parser.add_argument("--push", action='store_true', help="Push tools and/or workflows")
    export_parser.set_defaults(command='export')
    export_parser.set_defaults(resource='all')

    # publish command
    publish_parser = sp.add_parser("push",
                                   help="publish just exported tools and/or workflows",
                                   formatter_class=lambda prog: argparse.HelpFormatter(prog, width=140, max_help_position=100))
    publish_parser.add_argument("--to", dest="platform", choices=[o.value for o in _ALLOWED_SOURCES], required=True,
                                help="target platform for publishing tools and/or workflows")
    publish_parser.set_defaults(command='push')
    publish_parser.set_defaults(resource='all')

    # add resource_parser as subparser of the {export,publish}_pasers
    for parent_parser in [export_parser, publish_parser]:
        resource_subparsers = parent_parser.add_subparsers(
            title="types of resource to {}".format("export" if parent_parser == export_parser else "push"))
        all_res_parser = resource_subparsers.add_parser("all", help="tools and workflows (default)",
                                                        formatter_class=lambda prog: argparse.HelpFormatter(prog, width=140, max_help_position=100))
        all_res_parser.set_defaults(resource='all')

        tool_res_parser = resource_subparsers.add_parser("tools", help="tools")
        tool_res_parser.set_defaults(resource='tools')
        tool_res_parser.add_argument("--filter", help="list of comma separated tool IDs")

        wf_res_parser = resource_subparsers.add_parser("workflows", help="workflows")
        wf_res_parser.set_defaults(resource='workflows')
        wf_res_parser.add_argument("--filter", help="list of comma separated workflow IDs")

    return parser


def run():
    requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
    logging.getLogger("requests").setLevel(logging.ERROR)
    parser = build_cli_parser()
    args = parser.parse_args()
    # Append logger to the console if debug mode is enabled
    if args.debug:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.DEBUG)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    # configure log level
    logger.setLevel(logging.DEBUG if args.debug else logging.INFO)
    logger.debug("CLI options: %s", args)
    try:
        if "command" in args:
            globals()[args.command](args)
        else:
            parser.print_help()
            sys.exit(1)
    except KeyError as e:
        logger.error("Command '%s' not found", args.command)
        if logger.isEnabledFor(logging.DEBUG):
            logger.exception(e)
        parser.print_help()
        sys.exit(1)
    except KeyboardInterrupt as e:
        logger.error("'%s' command interrupted by user", args.command)
