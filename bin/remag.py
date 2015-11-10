#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on Jun. 16, 2014

@author: Olivia Doppelt-Azeroual, CIB-C3BI, Institut Pasteur, Paris
@author: Fabien Mareuil, CIB-C3BI, Institut Pasteur, Paris
@contact: fabien.mareuil@pasteur.fr
@project: ReGaTE
@githuborganization: bioinfo-center-pasteur-fr
"""

import string
import os
import sys
import yaml
import rdflib
import xml.etree.ElementTree as ET
import argparse
import ConfigParser

from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy.client import ConnectionError


def is_true(value):
    """
    :param value:
    :return:
    """
    return value.lower() == "true"


def is_edamtype(dic_child):
    """
    :param dic_child:
    :return:
    """
    if 'edam' in dic_child:
        if dic_child['edam'] not in ['', "None", "Null"]:
            return True
        else:
            return False
    else:
        return False


def return_formatted_edam(edam):
    """
    :param edam:
    :return:
    """
    edam = string.split(edam, '_')
    edam = "EDAM_{}:{:0>4d}".format(edam[0], int(edam[1]))
    return edam


def tsv_to_dict(edam_mapping_file, mapping_dict):
    """
    :param edam_mapping_file:
    :param mapping_dict:
    :return:
    """
    with open(edam_mapping_file, "r") as EG_MAPPING:
        for line in EG_MAPPING:
            splitted = string.split(line, '\t')
            if len(splitted) > 1 and splitted[0] not in ["GALAXY", "NAME", '"', "EXTENSION", '']:
                if splitted[1].strip() in ['']:
                    mapping_dict[splitted[0].strip()] = ["Not Mapped Yet"]
                else:
                    form_edam = return_formatted_edam(splitted[1].strip())
                    if splitted[0].strip() in mapping_dict:
                        if mapping_dict[splitted[0].strip()][0] != form_edam:
                            sys.stderr.write(
                                "MAPPING Incoherence between {} and {} for {} extension, {} have been chosen\n".format(
                                    mapping_dict[splitted[0].strip()][0], form_edam, splitted[0].strip(),
                                    mapping_dict[splitted[0].strip()][0]))

                    else:
                        mapping_dict[splitted[0].strip()] = [form_edam]
    return mapping_dict


def xml_to_dict(datatype_file_xml, mapping_dict):
    """
    :param datatype_file_xml:
    :param mapping_dict:
    :return:
    """
    tree = ET.parse(datatype_file_xml)
    root = tree.getroot()
    for child in root[0]:
        if 'display_in_upload' in child.attrib:
            if is_edamtype(child.attrib):
                edam_format = return_formatted_edam(child.attrib['edam'])
                if not child.attrib['extension'] in mapping_dict and is_true(child.attrib['display_in_upload']):
                    mapping_dict[child.attrib['extension']] = [edam_format]
                else:
                    if mapping_dict[child.attrib['extension']][0] != edam_format:
                        sys.stderr.write(
                            "XML Incoherence between {} and {} for {} extension, {} have been chosen\n".format(
                                mapping_dict[child.attrib['extension']][0], edam_format, child.attrib['extension'],
                                mapping_dict[child.attrib['extension']][0]))
            else:
                if not child.attrib['extension'] in mapping_dict and is_true(child.attrib['display_in_upload']):
                    mapping_dict[child.attrib['extension']] = ["Not Mapped Yet"]
    return mapping_dict


def http_to_edamform(url):
    """
    :param url:
    :return:
    """
    base = string.split(os.path.basename(url), '_')
    return str("EDAM_{}:{:0>4d}").format(base[0], int(base[1]))


def edam_to_dict(edam_file):
    """
    :param edam_file:
    :return:
    """
    g = rdflib.Graph()
    g.parse(edam_file)
    query1 = """SELECT ?format ?is_format_of WHERE {
                      ?format rdfs:subClassOf ?format_sc .
                      ?format_sc owl:onProperty
                          <http://edamontology.org/is_format_of> .
                      ?format_sc owl:someValuesFrom ?is_format_of
                      }"""
    query2 = """SELECT ?format ?superformat WHERE {
                      ?format rdfs:subClassOf ?superformat .
                      ?superformat oboInOwl:inSubset <http://purl.obolibrary.org/obo/edam#formats>
                      }"""
    # Property = {"oboInOwl": "http://www.geneontology.org/formats/oboInOwl#"}
    format_with_formats = {}
    format_with_data = {}
    for row in g.query(query1):
        format_with_data[http_to_edamform(row[0])] = http_to_edamform(row[1])
    for row in g.query(query2):
        child_format = http_to_edamform(row[0])
        parent_format = http_to_edamform(row[1])
        if child_format in format_with_formats:
            format_with_formats[child_format].append(parent_format)
        else:
            format_with_formats[child_format] = [parent_format]
    return format_with_formats, format_with_data


def add_data(formats, relation_formats, relation_data, list_edam_data):
    """
    :param formats:
    :param relation_formats:
    :param relation_data:
    :param list_edam_data:
    :return:
    """
    if len(formats) != 0:
        for format_tool in formats:
            if format_tool in relation_data:
                list_edam_data.append(relation_data[format_tool])
                formats.remove(format_tool)
                return add_data(formats, relation_formats, relation_data, list_edam_data)
            elif format_tool in relation_formats:
                formats.remove(format_tool)
                formats = formats + relation_formats[format_tool]
                return add_data(formats, relation_formats, relation_data, list_edam_data)
            else:
                sys.stdout.write("NO FORMAT AND NO DATA FOR {}\n".format(format_tool))
                formats.remove(format_tool)
                if format_tool in ("Not Mapped Yet", "NONE Known"):
                    return add_data(formats, relation_formats, relation_data, list_edam_data)
                else:
                    list_edam_data.append("EDAM_data:0006")
                    return add_data(formats, relation_formats, relation_data, list_edam_data)
    else:
        return list_edam_data


def add_datas(dict_map, relation_format_formats, relation_format_data):
    """
    :param dict_map:
    :param relation_format_formats:
    :param relation_format_data:
    :return:
    """
    import copy
    for key, value in dict_map.iteritems():
        formats = copy.copy(value)
        datas = add_data(formats, relation_format_formats, relation_format_data, list_edam_data=[])
        dict_map[key] = value + datas
    return dict_map


def dict_to_yaml(mapping_dict, yamlfile):
    """
    :param mapping_dict:
    :param yamlfile:
    :return:
    """
    stream = file(yamlfile, 'w')
    yaml.dump(mapping_dict, stream, default_flow_style=False)


def galaxy_to_edamdict(url, key, dict_map=None):
    """
    :param url:
    :param key:
    :param dict_map:
    :return:
    """
    if not dict_map:
        dict_map = {}
    gi = GalaxyInstance(url, key=key)
    try:
        dict_map = gi.datatypes.get_edam_formats()
    except AttributeError, e:
        sys.stderr.write(
            '{}, The Galaxy data can\'t be used, It\'s \
            possible that your bioblend version is too old, please update it\n'.format(
                e))
    except ConnectionError, e:
        sys.stderr.write(
            '{}, The Galaxy data can\'t be used, It\'s possible that Galaxy is too old, please update it\n'.format(e))
    dictmapping = {}
    for key, value in dict_map.iteritems():
        form_edam = return_formatted_edam(value)
        dictmapping[str(key)] = [form_edam]
    return dictmapping

def generate_template():
    """
    :return:
    """
    TEMPLATE_CONFIG = os.path.join(os.path.dirname(__file__),'regate.ini')
    print TEMPLATE_CONFIG
    config = ConfigParser.ConfigParser(allow_no_value = True)
    config.read(TEMPLATE_CONFIG)
    with open('regate.ini', 'w') as fp:
        config.write(fp)


    with open('regate.ini', 'w') as fp:
        config.write(fp)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Galaxy instance tool\
        parsing, for integration in biotools/bioregistry")

    parser.add_argument("--galaxy_url", help="url to the analyze \
        galaxy instance")

    parser.add_argument("--api_key", help="galaxy user api key")

    parser.add_argument("--output_yaml", help="output file format yaml")

    parser.add_argument("--datatype_conf", help="datatype_conf with \
        edam format")

    parser.add_argument("--edam_file", help="edam owl file to create  \
        the edam_dict")

    parser.add_argument("--mapping_file", help="mapping file format tsv  \
        extension edam_format description")

    parser.add_argument("--config", help="config file")

    parser.add_argument("--templateconfig", action='store_true', help="generate a config file template")

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)

    args = parser.parse_args()
    if not args.templateconfig:
        if args.galaxy_url and args.api_key:
            dict_mapping = galaxy_to_edamdict(args.galaxy_url, args.api_key)
        else:
            dict_mapping = {}
        relation_format_formats, relation_format_data = edam_to_dict(args.edam_file)
        if args.mapping_file:
            dict_mapping = tsv_to_dict(args.mapping_file, dict_mapping)
        if args.datatype_conf:
            dict_mapping = xml_to_dict(args.datatype_conf, dict_mapping)
            yaml_file = args.output_yaml
            dict_mapping = add_datas(dict_mapping, relation_format_formats, relation_format_data)

        dict_to_yaml(dict_mapping, yaml_file)
    else:
        generate_template()
