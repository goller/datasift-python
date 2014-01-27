#!/usr/bin/env python
from __future__ import print_function
import sys, os

if sys.version_info < (2, 7):
    import unittest2 as unittest
else:
    import unittest

from bs4 import BeautifulSoup
import re, requests, time, json

from httmock import response, all_requests, urlmatch, HTTMock

from unittest import TestCase
from datasift import DataSiftClient, DataSiftConfig
from datasift.exceptions import *
from requests import HTTPError
from requests.auth import HTTPBasicAuth

from tests.mocks import *

GITHUB_TOKEN=os.environ.get("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    sys.stderr.write("Please export a github OAUTH token as GITHUB_TOKEN to run these tests")
    sys.exit(1)

# Helper methods
def get_all_gists_on_page(url):
    r = requests.get(url)
    soup = BeautifulSoup(r.content)
    gist_js = soup.find_all("script", src=re.compile("gist"))
    gists = map(lambda x: x["src"].replace(".js", "").replace("gist.github.com/","api.github.com/gists/"), gist_js)
    data = map(lambda x: requests.get(x+"?access_token="+GITHUB_TOKEN).json(), gists)
    data = filter(lambda x:x[u"files"][list(x["files"].keys())[0]]["language"] == "JSON", data)
    data = map(lambda x:json.loads(x[u"files"][list(x["files"].keys())[0]]["content"]) ,data)
    return data

def find_api_doc_of(function):
    if not hasattr(function, "__doc__"):
        return None
    docstring = function.__doc__
    devlinks = filter(lambda x:x.startswith("http://dev.datasift.com/docs"), docstring.split())
    for item in devlinks:
        return item

def mock_output_of(function):
    """ Takes a function and generates a mock suitable for use with it.

        Returns the mock function and the list of results to expect out, in order
    """
    documentation = find_api_doc_of(function)
    gists = list(get_all_gists_on_page(documentation))
    internal = gists.__iter__()

    @all_requests
    def mocked_response(url, content):
        return response(200, next(internal), {'content-type': 'application/json'}, None, 5, content)
    return mocked_response, list(gists)

def assert_dict_structure(testcase, structure, data):
    for key in structure:
        assert (key in data)
        if key in data:
            if isinstance(key, dict):
                assert_dict_structure(testcase, structure[key], data[key])

# TestCases

class TestMockedClient(TestCase):
    def setUp(self):
        TestCase.setUp(self)
        self.client = DataSiftClient(DataSiftConfig("testuser", "testapikey"))

    def test_creation_of_client(self):
        self.assertTrue(self.client)

    def test_handling_of_authorization_failed(self):
        with HTTMock(authorization_failed):
            self.assertRaises(AuthException, self.client.balance)

    def test_output_of_balance(self):
        mock, expected = mock_output_of(self.client.balance)
        with HTTMock(mock):
            runs = 0
            for expecteditem in expected:
                runs += 1
                results = self.client.balance()
                assert_dict_structure(self, results, expecteditem)
            self.assertNotEqual(runs, 0, "ensure that at least one case was tested")

    def test_compile_with_valid_output(self):
        mock, expected = mock_output_of(self.client.compile)
        with HTTMock(mock):
            runs = 0
            for item in expected:
                runs += 1
                assert_dict_structure(self, item, self.client.compile("dummy csdl that is valid"))
            self.assertNotEqual(runs, 0, "ensure that at least one case was tested")

    def test_compile_invalid_csdl(self):
        with HTTMock(failed_compilation_of_csdl):
            self.assertRaises(DataSiftApiException, self.client.compile, ("dummy csdl which is bad"))

    def test_is_valid_csdl_with_bad_data(self):
        with HTTMock(failed_compilation_of_csdl):
            self.assertFalse(self.client.is_valid("dummy csdl which is bad"))

    def test_is_valid_csdl_with_good_data(self):
        mock, expected = mock_output_of(self.client.validate)
        with HTTMock(mock):
            runs = 0
            for item in expected:
                runs+=1
                r = self.client.is_valid("dummy csdl which is valid")
                self.assertTrue(r)
            self.assertNotEqual(runs, 0, "ensure that at least one case was tested")

    def test_is_valid_csdl_cause_exception(self):
        with HTTMock(internal_server_error_with_json):
            self.assertRaises(DataSiftApiException, self.client.is_valid, ("csdl which turns into a teapot"))

    def test_error_handling_of_internal_server_errors(self):
        with HTTMock(internal_server_error):
            self.assertRaises(DataSiftApiFailure, self.client.balance)

    def test_error_handling_of_weird_errors(self):
        with HTTMock(weird_error):
            self.assertRaises(HTTPError, self.client.validate, ("csdl which turns into a teapot"))

    def test_client_usage(self):
        mock, expected = mock_output_of(self.client.usage)
        with HTTMock(mock):
            runs = 0
            for expected_output in expected:
                runs += 1
                results = self.client.usage()
                assert_dict_structure(self, results, expected_output)
            self.assertNotEqual(runs, 0, "ensure that at least one case was tested")

    def test_client_usage_with_parameter(self):
        mock, expected = mock_output_of(self.client.usage)
        with HTTMock(mock):
            runs = 0
            for expected_output in expected:
                runs += 1
                results = self.client.usage(period="day")
                assert_dict_structure(self, results, expected_output)
            self.assertNotEqual(runs, 0, "ensure that at least one case was tested")


    def test_client_dpu(self):
        mock, expected = mock_output_of(self.client.dpu)
        with HTTMock(mock):
            runs = 0
            for expected_output in expected:
                runs += 1
                results = self.client.dpu("valid stream id")
                assert_dict_structure(self, results, expected_output)
            self.assertNotEqual(runs, 0, "ensure that at least one case was tested")

    @unittest.skipIf(sys.version_info >= (3,0), "Mocking requests does not work correctly on py3")
    def test_client_pull(self):
        mock, expected = normal_pull_output()
        with HTTMock(mock):
            results = self.client.pull("dummy valid subscription id", size=2048, cursor=512)
            self.assertEquals(results.status_code, 200)
            self.assertEqual(len(results), len(expected), msg="get the same number of interactions out")
            for output, expected in zip(results, expected):
                assert_dict_structure(self, output, expected)

    def test_historics_prepare(self):
        mock, expected = mock_output_of(self.client.historics.prepare)
        with HTTMock(mock):
            runs = 0
            for expected_output in expected:
                runs += 1
                results = self.client.historics.prepare("fake csdl hash", int(time.time()-60), int(time.time()), "my fake historics query", ["twitter"], sample=10)
                assert_dict_structure(self, results, expected_output)
            self.assertNotEqual(runs, 0, "ensure that at least one case was tested")


    def test_live_streaming_exceptions_warn_on_bad_starts(self):
        self.assertRaises(StreamSubscriberNotStarted, self.client.subscribe, ("hash"))
        self.client._stream_process_started = True
        func = self.client.subscribe("hash")
        self.assertRaises(DeleteRequired, func, ("hash"))

    def test_live_streaming_client_setup(self):
        mock, expected = mock_output_of(self.client.compile)

        with HTTMock(mock):
            @self.client.on_delete
            def on_delete(interaction):
                print( 'Deleted interaction %s ' % interaction)


            @self.client.on_open
            def on_open():
                print( 'Streaming ready, can start subscribing')
                csdl = 'interaction.content contains "music"'
                stream = self.client.compile(csdl)['hash']

                @self.client.subscribe(stream)
                def subscribe_to_hash(msg):
                    print(msg)


            @self.client.on_closed
            def on_close(wasClean, code, reason):
                print('Streaming connection closed')


            @self.client.on_ds_message
            def on_ds_message(msg):
                print('DS Message %s' % msg)

            self.client._stream_process_started = True
            self.client.start_stream_subscriber()


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMockedClient)
    unittest.TextTestRunner(verbosity=2).run(suite)
