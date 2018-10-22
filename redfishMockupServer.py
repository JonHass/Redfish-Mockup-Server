# Copyright Notice:
# Copyright 2016 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Mockup-Server/blob/master/LICENSE.md

# redfishMockupServer.py
# tested and developed Python 3.4

import urllib
import sys
import getopt
import time
import collections
import json
import requests
import posixpath
import threading

import os
import ssl
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, urlunparse, parse_qs
from rfSsdpServer import RfSDDPServer

patchedLinks = dict()

tool_version = "1.0.6"

dont_send = ["connection", "keep-alive", "content-length", "transfer-encoding"]


def get_cached_link(path):
    if path not in patchedLinks:
        if os.path.isfile(path):
            with open(path) as f:
                jsonData = json.load(f)
                f.close()
        else:
            jsonData = None
    else:
        jsonData = patchedLinks[path]
    return jsonData is not None and jsonData != '404', jsonData


def dict_merge(dct, merge_dct):
        """
        https://gist.github.com/angstwad/bf22d1822c38a92ec0a9 modified
        Recursive dict merge. Inspired by :meth:``dict.update()``, instead of
        updating only top-level keys, dict_merge recurses down into dicts nested
        to an arbitrary depth, updating keys. The ``merge_dct`` is merged into
        ``dct``.
        :param dct: dict onto which the merge is executed
        :param merge_dct: dct merged into dct
        :return: None
        """
        for k in merge_dct:
            if (k in dct and isinstance(dct[k], dict) and isinstance(merge_dct[k], collections.Mapping)):
                dict_merge(dct[k], merge_dct[k])
            else:
                dct[k] = merge_dct[k]


def clean_path(path, isShort):
    path = path.strip('/')
    path = path.split('?', 1)[0]
    path = path.split('#', 1)[0]
    if isShort:
        path = path.replace('redfish/v1/', '')
        path = path.replace('redfish/v1', '')
    return path


class RfMockupServer(BaseHTTPRequestHandler):
        '''
        returns index.json file for Serverthe specified URL
        '''
        server_version = "RedfishMockupHTTPD_v" + tool_version
        event_id = 1

        # Headers only request
        def do_HEAD(self):
            print("Headers: ")
            sys.stdout.flush()

            # construct path "mockdir/path/to/resource/headers.json"
            rfile = "headers.json"
            rpath = clean_path(self.path, self.server.shortForm)
            apath = self.server.mockDir
            fpath = os.path.join(apath, rpath, rfile)

            if self.server.timefromJson:
                responseTime = self.getResponseTime('HEAD', apath, rpath)
                try:
                    time.sleep(float(responseTime))
                except ValueError as e:
                    print("Time is not a float value. Sleeping with default response time")
                    time.sleep(float(self.server.responseTime))

            sys.stdout.flush()
            print(self.server.headers)

            # If bool headers is true and headers.json exists...
            if self.server.headers and (os.path.isfile(fpath)):
                self.send_response(200)
                with open(fpath) as headers_data:
                    d = json.load(headers_data)
                if isinstance(d["GET"], dict):
                    for k, v in d["GET"].items():
                        if k.lower() not in dont_send:
                            self.send_header(k, v)
                self.end_headers()
            elif (self.server.headers is False) or (os.path.isfile(fpath) is False):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("OData-Version", "4.0")
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def do_GET(self):
            # for GETs always dump the request headers to the console
            # there is no request data, so no need to dump that
            print("   GET: Headers: {}".format(self.headers))
            sys.stdout.flush()
            # specify headers to not send (use lowercase)
            rfile = "index.json"
            rfileXml = "index.xml"
            rhfile = "headers.json"

            # construct path "mockdir/path/to/resource/<filename>"
            # this is the resource path
            rpath = clean_path(self.path, self.server.shortForm)
            # this is the real absolute path to the mockup directory
            apath = self.server.mockDir
            # form the path in the mockup of the file
            #      old only support mockup in CWD:  apath=os.path.abspath(rpath)
            fpath = os.path.join(apath, rpath, rfile)
            fhpath = os.path.join(apath, rpath, rhfile)
            fpathxml = os.path.join(apath, rpath, rfileXml)
            fpathdirect = os.path.join(apath, rpath)

            scheme, netloc, path, params, query, fragment = urlparse(self.path)
            query_pieces = parse_qs(query, keep_blank_values=True)

            # get the testEtagFlag and mockup directory path parameters passed in from the http server
            testEtagFlag = self.server.testEtagFlag

            if self.server.timefromJson:
                responseTime = self.getResponseTime('GET', apath, rpath)
                try:
                    time.sleep(float(responseTime))
                except ValueError as e:
                    print("Time is not a float value. Sleeping with default response time.")
                    time.sleep(float(self.server.responseTime))

            # handle resource paths that don't exist for shortForm
            # '/' and '/redfish'
            if(self.path == '/' and self.server.shortForm):
                self.send_response(404)
                self.end_headers()

            elif(self.path in ['/redfish', '/redfish/'] and self.server.shortForm):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({'v1': '/redfish/v1'}, indent=4).encode())

            # if this location exists in memory or as file
            elif(os.path.isfile(fpath) or fpath in patchedLinks):
                # if patchedLink is not deleted, else 404
                # fallthrough case: will be 200 for files too
                self.send_response(200 if patchedLinks.get(fpath) != '404' else 404)

                # special cases to test etag for testing
                # if etag is returned then the patch to these resources should include this etag
                if testEtagFlag:
                        if(self.path == "/redfish/v1/Systems/1"):
                                self.send_header("Etag", "W/\"12345\"")
                        elif(self.path == "/redfish/v1/AccountService/Accounts/1"):
                                self.send_header("Etag", "\"123456\"")

                # if headers exist... send information (except for chunk info)
                # end headers here (always end headers after response)
                if self.server.headers and (os.path.isfile(fhpath)):
                    with open(fhpath) as headers_data:
                        d = json.load(headers_data)
                    if isinstance(d["GET"], dict):
                        for k, v in d["GET"].items():
                            if k.lower() not in dont_send:
                                self.send_header(str(k), str(v))
                elif (os.path.isfile(fhpath) is False):
                    self.send_header("Content-Type", "application/json")
                    self.send_header("OData-Version", "4.0")
                self.end_headers()

                # then grab output from file or patchedLinks
                if fpath not in patchedLinks:
                    f = open(fpath, "r")
                    json_obj = json.loads(f.read())
                    output_data = json_obj
                    f.close()
                else:
                    if patchedLinks[fpath] not in [None, '404']:
                        output_data = patchedLinks[fpath]
                    else:
                        output_data = {}

                # Strip the @Redfish.Copyright property
                output_data.pop("@Redfish.Copyright", None)

                if output_data.get('Members') is not None:
                    my_members = output_data['Members']
                    top_count = int(query_pieces.get('$top', [str(len(my_members))])[0])
                    top_skip = int(query_pieces.get('$skip', ['0'])[0])

                    my_members = my_members[top_skip:]
                    if top_count < len(my_members):
                        my_members = my_members[:top_count]
                        query_out = {'$skip': top_skip + top_count, '$top': top_count}
                        query_string = '&'.join(['{}={}'.format(k, v) for k, v in query_out.items()])
                        output_data['Members@odata.nextLink'] = urlunparse(('', '', path, '', query_string, ''))
                    else:
                        pass

                    output_data['Members'] = my_members
                    pass

                encoded_data = json.dumps(output_data, sort_keys=True, indent=4, separators=(",", ": ")).encode()
                self.wfile.write(encoded_data)

            # if XML...
            elif(os.path.isfile(fpathxml) or os.path.isfile(fpathdirect)):
                if os.path.isfile(fpathxml):
                    file_extension = 'xml'
                    f = open(fpathxml, "r")
                elif os.path.isfile(fpathdirect):
                    filename, file_extension = os.path.splitext(fpathdirect)
                    f = open(fpathdirect, "r")
                self.send_response(200)
                self.send_header("Content-Type", "application/" + file_extension + ";odata.metadata=minimal;charset=utf-8")
                self.end_headers()
                self.wfile.write(f.read().encode())
                f.close()
            else:
                self.send_response(404)
                self.end_headers()

        def do_PATCH(self):
                print("   PATCH: Headers: {}".format(self.headers))
                responseTime = self.server.responseTime
                time.sleep(responseTime)

                if("content-length" in self.headers):
                    lenn = int(self.headers["content-length"])
                    dataa = json.loads(self.rfile.read(lenn).decode("utf-8"))
                    print("   PATCH: Data: {}".format(dataa))

                    # construct path "mockdir/path/to/resource/<filename>"
                    rpath = clean_path(self.path, self.server.shortForm)
                    apath = self.server.mockDir    # this is the real absolute path to the mockup directory
                    fpath = os.path.join(apath, rpath, 'index.json')

                    # check if resource exists, otherwise 404
                    #   if it's a file, open it, if its in memory, grab it
                    #   405 if Collection
                    #   204 if patch success
                    #   404 if payload DNE
                    # end headers
                    success, jsonData = get_cached_link(fpath)
                    if success:
                        # If this is a collection, throw a 405
                        if jsonData.get('Members') is not None:
                            self.send_response(405)
                        else:
                            # After getting resource, merge the data.
                            print(self.headers.get('content-type'))
                            print(dataa)
                            print(jsonData)
                            dict_merge(jsonData, dataa)
                            print(jsonData)
                            # put into patchedLinks
                            patchedLinks[fpath] = jsonData
                            self.send_response(204)
                    else:
                        self.send_response(404)

                self.end_headers()

        def do_PUT(self):
                print("   PUT: Headers: {}".format(self.headers))
                responseTime = self.server.responseTime
                time.sleep(responseTime)

                if("content-length" in self.headers):
                    lenn = int(self.headers["content-length"])
                    dataa = json.loads(self.rfile.read(lenn).decode("utf-8"))
                    print("   PUT: Data: {}".format(dataa))

                # we don't support this service
                #   405
                # end headers
                self.send_response(405)

                self.end_headers()

        def do_POST(self):
                print("   POST: Headers: {}".format(self.headers))
                if("content-length" in self.headers):
                        lenn = int(self.headers["content-length"])
                        dataa = json.loads(self.rfile.read(lenn).decode("utf-8"))
                        print("   POST: Data: {}".format(dataa))
                responseTime = self.server.responseTime
                time.sleep(responseTime)

                # construct path "mockdir/path/to/resource/<filename>"
                rpath = clean_path(self.path, self.server.shortForm)
                apath = self.server.mockDir    # this is the real absolute path to the mockup directory
                fpath = os.path.join(apath, rpath, 'index.json')

                xpath = rpath.rstrip('/')

                # don't bother if this item exists, otherwise, check if its an action or a file
                # if file
                #   405 if not Collection
                #   204 if success
                #   404 if no file present
                if os.path.isfile(fpath) or patchedLinks.get(fpath) is not None:
                    success, jsonData = get_cached_link(fpath)
                    if success:
                        if jsonData.get('Members') is None:
                            self.send_response(405)
                        else:
                            print(dataa)
                            print(type(dataa))
                            # with members, form unique ID
                            #   must NOT exist in Members
                            #   add ID to members, change count
                            #   store as necessary in patchedLinks
                            members = jsonData.get('Members')
                            n = 1
                            newpath = '/{}/{}'.format(xpath, len(members) + n)
                            while newpath in [m.get('@odata.id') for m in members]:
                                n = n + 1
                                newpath = '/{}/{}'.format(xpath, len(members) + n)
                            members.append({'@odata.id': newpath})

                            jsonData['Members'] = members
                            jsonData['Members@odata.count'] = len(members)

                            newfpath = os.path.join(newpath, 'index.json')
                            newfpath = apath + newfpath

                            print(newfpath)

                            if self.server.shortForm:
                                newfpath = newfpath.replace('redfish/v1/', '')

                            print(newfpath)

                            patchedLinks[newfpath] = dataa
                            patchedLinks[fpath] = jsonData
                            self.send_response(204)
                            self.send_header("Location", newpath)
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                    else:
                        self.send_response(404)

                # eventing framework
                else:
                    if 'EventService/Actions/EventService.SubmitTestEvent' in rpath:
                        eventpath = os.path.join(apath, 'redfish/v1/EventService/Subscriptions', 'index.json')
                        if self.server.shortForm:
                            eventpath = eventpath.replace('redfish/v1/', '')
                        success, jsonData = get_cached_link(eventpath)
                        print(eventpath)
                        if not success:
                            # Eventing not supported
                            self.send_response(404)
                        else:
                            # Check if all of the parameters are given
                            if ( ('EventType' not in dataa) or ('EventId' not in dataa) or
                                 ('EventTimestamp' not in dataa) or ('Severity' not in dataa) or
                                 ('Message' not in dataa) or ('MessageId' not in dataa) or
                                 ('MessageArgs' not in dataa) or ('OriginOfCondition' not in dataa) ):
                                self.send_response(400)
                            else:
                                # Need to reformat to make Origin Of Condition a proper link
                                origin_of_cond = dataa['OriginOfCondition']
                                dataa['OriginOfCondition'] = {}
                                dataa['OriginOfCondition']['@odata.id'] = origin_of_cond

                                # Go through each subscriber
                                print(jsonData.get('Members'))
                                for member in jsonData.get('Members', []):
                                    entry = member['@odata.id']
                                    if self.server.shortForm:
                                        entry = entry.replace('redfish/v1/', '')
                                    entrypath = os.path.join(apath + entry, 'index.json')
                                    success, jsonData = get_cached_link(entrypath)
                                    print(apath)
                                    print(entrypath)
                                    if not success:
                                        print('No such resource')
                                    else:
                                        # Sanity check the subscription for required properties
                                        if ('Destination' in jsonData) and ('EventTypes' in jsonData):
                                            print('Target', jsonData['Destination'])
                                            print(dataa['EventType'], jsonData['EventTypes'])

                                            # If the EventType in the request is one of interest to the subscriber, build an event payload
                                            if dataa['EventType'] in jsonData['EventTypes']:
                                                event_payload = {}
                                                event_payload['@odata.type'] = '#Event.v1_2_1.Event'
                                                event_payload['Id'] = str(self.event_id)
                                                event_payload['Name'] = 'Test Event'
                                                event_payload['Context'] = jsonData.get('Context', 'Default Context')
                                                event_payload['Events'] = []
                                                event_payload['Events'].append(dataa)
                                                http_headers = {}
                                                http_headers['Content-Type'] = 'application/json'

                                                # Send the event
                                                try:
                                                    r = requests.post(jsonData['Destination'], timeout=20, data=json.dumps(event_payload), headers=http_headers)
                                                    print('post complete', r.status_code)
                                                except Exception as e:
                                                    print('post error', str(e))
                                            else:
                                                print('event not in eventtypes')
                                    sys.stdout.flush()
                                self.send_response(204)
                                self.event_id = self.event_id + 1
                    elif 'TelemetryService/Actions/TelemetryService.SubmitTestMetricReport' in rpath:
                        eventpath = os.path.join(apath, 'redfish/v1/EventService/Subscriptions', 'index.json')
                        if self.server.shortForm:
                            eventpath = eventpath.replace('redfish/v1/', '')
                        success, jsonData = get_cached_link(eventpath)
                        print(eventpath)
                        if not success:
                            # Eventing not supported
                            self.send_response(404)
                        else:
                            # Check if all of the parameters are given
                            if ('Name' not in dataa) or ('Value' not in dataa):
                                self.send_response(400)
                            else:
                                print(jsonData.get('Members'))
                                for member in jsonData.get('Members', []):
                                    entry = member['@odata.id']
                                    if self.server.shortForm:
                                        entry = entry.replace('redfish/v1/', '')
                                    entrypath = os.path.join(apath + entry, 'index.json')
                                    success, jsonData = get_cached_link(entrypath)
                                    print(apath)
                                    print("entrypath", entrypath)
                                    if not success:
                                        print('No such resource')
                                    else:
                                        # Sanity check the subscription for required properties
                                        if ('Destination' in jsonData) and ('EventTypes' in jsonData):
                                            print('Target', jsonData['Destination'])

                                            # If the EventType in the request is one of interest to the subscriber, build an event payload
                                            event_payload = {}
                                            value_list = []
                                            event_payload[
                                                '@Redfish.Copyright'] = 'Copyright 2014-2016 Distributed Management Task Force, Inc. (DMTF). All rights reserved.'
                                            event_payload['@odata.context'] = '/redfish/v1/$metadata#MetricReport.MetricReport'
                                            event_payload['@odata.type'] = '#MetricReport.v1_0_0.MetricReport'
                                            event_payload['@odata.id'] = '/redfish/v1/TelemetryService/MetricReports/' + dataa[
                                                'Name']
                                            event_payload['Id'] = dataa['Name']
                                            event_payload['Name'] = dataa['Name']
                                            event_payload['EventTimestamp'] = dataa['EventTimestamp']
                                            event_payload['MetricReportDefinition'] = {
                                                "@odata.id": "/redfish/v1/TelemetryService/MetricReportDefinitions/" + dataa[
                                                    'Name']}
                                            for tup in dataa['Value']:
                                                item = {}
                                                item['MemberID'] = tup[0]
                                                item['MetricValue'] = tup[1]
                                                item['TimeStamp'] = tup[2]
                                                if len(tup) == 4:
                                                    item['MetricProperty'] = tup[3]
                                                value_list.append(item)
                                            event_payload['MetricValues'] = value_list
                                            print(event_payload)
                                            http_headers = {}
                                            http_headers['Content-Type'] = 'application/json'

                                            try:
                                                r = requests.post(jsonData['Destination'], timeout=20,
                                                                  data=json.dumps(event_payload), headers=http_headers)
                                                print('post complete', r.status_code)
                                            except Exception as e:
                                                print('post error', str(e))
                                    sys.stdout.flush()
                                self.send_response(204)
                                self.event_id = self.event_id + 1
                    else:
                        self.send_response(405)

                self.end_headers()

        def do_DELETE(self):
                """
                Delete a resource
                """
                print("DELETE: Headers: {}".format(self.headers))
                if("content-length" in self.headers):
                        dataa = {}
                        print("   POST: Data: {}".format(dataa))

                responseTime = self.server.responseTime
                time.sleep(responseTime)

                # construct path
                # xpath is URI as related to redfish @odata.id
                rpath = clean_path(self.path)
                xpath = '/' + rpath
                if self.server.shortForm:
                    rpath = rpath.replace('redfish/v1/', '')
                    rpath = rpath.replace('redfish/v1', '')
                apath = self.server.mockDir    # this is the real absolute path to the mockup directory
                fpath = os.path.join(apath, rpath, 'index.json')

                parentpath = os.path.join(apath, rpath.rsplit('/', 1)[0], 'index.json')

                # 404 if file doesn't exist
                # 204 if success, override payload with 404
                #   modify payload to exclude expected URI, subtract count
                # 405 if parent is not Collection
                # end headers
                success, jsonData = get_cached_link(fpath)
                if success:
                    success, parentData = get_cached_link(parentpath)
                    if success and parentData.get('Members') is not None:
                        patchedLinks[fpath] = '404'
                        parentData['Members'] = [x for x in parentData['Members'] if not x['@odata.id'] == xpath]
                        parentData['Members@odata.count'] = len(parentData['Members'])
                        patchedLinks[parentpath] = parentData
                        self.send_response(204)
                    else:
                        self.send_response(405)
                else:
                    self.send_response(404)

                self.end_headers()

        # this is currently not used
        def translate_path(self, path):
                """
                Translate a /-separated PATH to the local filename syntax.
                Components that mean special things to the local file system
                (e.g. drive or directory names) are ignored.  (XXX They should
                probably be diagnosed.)
                """
                # abandon query parameters
                path = path.split('?', 1)[0]
                path = path.split('#', 1)[0]
                path = posixpath.normpath(urllib.unquote(path))
                words = path.split('/')
                words = filter(None, words)
                path = os.getcwd()
                for word in words:
                        drive, word = os.path.splitdrive(word)
                        head, word = os.path.split(word)
                        if word in (os.curdir, os.pardir):
                            continue
                path = os.path.join(path, word)
                return path

        # Response time calculation Algorithm
        def getResponseTime(self, method, apath, rpath):
                rfile = "time.json"
                fpath = os.path.join(apath, rpath, rfile)
                if not any(x in method for x in ("GET", "HEAD", "POST", "PATCH", "DELETE")):
                    print("Not a valid method")
                    return (0)

                if(os.path.isfile(fpath)):
                    with open(fpath) as time_data:
                        d = json.load(time_data)
                        time_str = method + "_Time"
                        if time_str in d:
                            try:
                                float(d[time_str])
                            except Exception as e:
                                print(
                                    "Time in the json file, not a float/int value. Reading the default time.")
                                return (self.server.responseTime)
                            return (float(d[time_str]))
                return (self.server.responseTime)


def usage(program):
        print("usage: {}   [-h][-P][-H <hostIpAddr>:<port>]".format(program))
        print("      -h --help      # prints usage ")
        print("      -L --Load      # <not implemented yet>: load and Dump json read from mockup in pretty format with indent=4")
        print("      -H <IpAddr>   --Host=<IpAddr>    # hostIP, default: 127.0.0.1")
        print("      -p <port>     --port=<port>      # port:  default is 8000")
        print("      -D <dir>,     --Dir=<dir>        # Path to the mockup directory. It may be relative to CWD")
        print("      -X,           --headers          # Option to load headers or not from json files")
        print("      -t <delay>    --time=<delayTime> # Delay Time in seconds added to any request. Must be float or int.")
        print("      -E            --TestEtag         # etag testing--enable returning etag for certain APIs for testing.  See Readme")
        print("      -T                               # Option to delay response or not.")
        print("      -s            --ssl              # Places server in https, requires a certificate and key")
        print("      --cert <cert>                    # Specify a certificate for ssl server function")
        print("      --key <key>                      # Specify a key for ssl")
        print("      -S            --shortForm        # Apply shortform to mockup (allowing to omit filepath /redfish/v1)")
        print("      -P            --ssdp             # Make mockup ssdp discoverable (by redfish specification)")
        sys.stdout.flush()


def main(argv):
        hostname = "127.0.0.1"
        port = 8000
        load = False
        program = argv[0]
        print(program)
        mockDirPath = None
        sslMode = False
        sslCert = None
        sslKey = None
        mockDir = None
        testEtagFlag = False
        responseTime = 0
        timefromJson = False
        headers = False
        shortForm = False
        ssdpStart = False
        print("Redfish Mockup Server, version {}".format(tool_version))
        try:
            opts, args = getopt.getopt(argv[1:], "hLTSPsEH:p:D:t:X", ["help", "Load", "shortForm", "ssdp", "ssl", "TestEtag", "headers", "Host=", "Port=", "Dir=",
                                                                    "time=", "cert=", "key="])
        except getopt.GetoptError:
            # usage()
            print("Error parsing options", file=sys.stderr)
            sys.stderr.flush()
            usage(program)
            sys.exit(2)

        for opt, arg in opts:
            if opt in ("-h", "--help"):
                usage(program)
                sys.exit(0)
            elif opt in ("L", "--Load"):
                load = True
            elif opt in ("-H", "--Host"):
                hostname = arg
            elif opt in ("-X", "--headers"):
                headers = True
            elif opt in ("-p", "--port"):
                port = int(arg)
            elif opt in ("-D", "--Dir"):
                mockDirPath = arg
            elif opt in ("-E", "--TestEtag"):
                testEtagFlag = True
            elif opt in ("-t", "--time"):
                responseTime = arg
            elif opt in ("-T"):
                timefromJson = True
            elif opt in ("-s", "--ssl"):
                sslMode = True
            elif opt in ("--cert",):
                sslCert = arg
            elif opt in ("--key",):
                sslKey = arg
            elif opt in ("-S", "--shortForm"):
                shortForm = True
            elif opt in ("-P", "--ssdp"):
                ssdpStart = True
            else:
                print('unhandled option', file=sys.stderr)
                sys.exit(2)

        print('program: ', program)
        print('Hostname:', hostname)
        print('Port:', port)
        print("dir path specified by user:{}".format(mockDirPath))
        print("response time: {} seconds".format(responseTime))
        sys.stdout.flush()

        # check if mockup path was specified.  If not, use current working directory
        if mockDirPath is None:
            mockDirPath = os.getcwd()

        # create the full path to the top directory holding the Mockup
        mockDir = os.path.realpath(mockDirPath)  # creates real full path including path for CWD to the -D<mockDir> dir path
        print("Serving Mockup in abs real directory path:{}".format(mockDir))

        # check that we have a valid tall mockup--with /redfish in mockDir before proceeding
        if not shortForm:
            slashRedfishDir = os.path.join(mockDir, "redfish")
            if os.path.isdir(slashRedfishDir) is not True:
                print("ERROR: Invalid Mockup Directory--no /redfish directory at top. Aborting", file=sys.stderr)
                sys.stderr.flush()
                sys.exit(1)

        if shortForm:
            if os.path.isdir(mockDir) is not True or os.path.isfile(os.path.join(mockDir, "index.json")) is not True:
                print("ERROR: Invalid Mockup Directory--dir or index.json does not exist", file=sys.stderr)
                sys.stderr.flush()
                sys.exit(1)

        myServer = HTTPServer((hostname, port), RfMockupServer)

        if sslMode:
            print("Using SSL with certfile: {}".format(sslCert))
            myServer.socket = ssl.wrap_socket(myServer.socket, certfile=sslCert, keyfile=sslKey, server_side=True)

        # save the test flag, and real path to the mockup dir for the handler to use
        myServer.mockDir = mockDir
        myServer.testEtagFlag = testEtagFlag
        myServer.headers = headers
        myServer.timefromJson = timefromJson
        myServer.shortForm = shortForm
        try:
            myServer.responseTime = float(responseTime)
        except ValueError as e:
            print("Enter a integer or float value")
            sys.exit(2)
        # myServer.me="HELLO"

        mySDDP = None
        if ssdpStart:
            # construct path "mockdir/path/to/resource/<filename>"
            rpath = clean_path('/redfish/v1', myServer.shortForm)
            # this is the real absolute path to the mockup directory
            apath = myServer.mockDir
            # form the path in the mockup of the file
            #      old only support mockup in CWD:  apath=os.path.abspath(rpath)
            fpath = os.path.join(apath, rpath, 'index.json')
            success, item = get_cached_link(fpath)
            protocol = '{}://'.format('https' if sslMode else 'http')
            mySDDP = RfSDDPServer(item, '{}{}:{}{}'.format(protocol, hostname, port, '/redfish/v1'), hostname)

        print("Serving Redfish mockup on port: {}".format(port))
        sys.stdout.flush()
        try:
            if mySDDP is not None:
                t2 = threading.Thread(target=mySDDP.start)
                t2.daemon = True
                t2.start()
            print('running Server...')
            myServer.serve_forever()

        except KeyboardInterrupt:
            pass

        myServer.server_close()
        print("Shutting down http server")
        sys.stdout.flush()


# the below is only executed if the program is run as a script
if __name__ == "__main__":
        main(sys.argv)

'''
TODO:
1. add -L option to load json and dump output from python dictionary
2. add authentication support -- note that in redfish some api don't require auth
3. add https support


'''
