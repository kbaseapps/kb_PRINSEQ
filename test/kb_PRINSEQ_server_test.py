# -*- coding: utf-8 -*-
import os  # noqa: F401
import shutil
import time
import unittest
from configparser import ConfigParser  # py3
from os import environ

import requests

from installed_clients.DataFileUtilClient import DataFileUtil
from installed_clients.ReadsUtilsClient import ReadsUtils
from installed_clients.WorkspaceClient import Workspace as workspaceService
from installed_clients.baseclient import ServerError as DFUError
from kb_PRINSEQ.authclient import KBaseAuth as _KBaseAuth
from kb_PRINSEQ.kb_PRINSEQImpl import kb_PRINSEQ
from kb_PRINSEQ.kb_PRINSEQServer import MethodContext


class kb_PRINSEQTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = environ.get('KB_AUTH_TOKEN', None)
        config_file = environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('kb_PRINSEQ'):
            cls.cfg[nameval[0]] = nameval[1]
        authServiceUrl = cls.cfg.get('auth-service-url',
                "https://kbase.us/services/authorization/Sessions/Login")
        auth_client = _KBaseAuth(authServiceUrl)
        user_id = auth_client.get_user(cls.token)
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': cls.token,
                        'user_id': user_id,
                        'provenance': [
                            {'service': 'kb_PRINSEQ',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        cls.shockURL = cls.cfg['shock-url']
        cls.wsURL = cls.cfg['workspace-url']
        cls.wsClient = workspaceService(cls.wsURL, token=cls.token)
        cls.serviceImpl = kb_PRINSEQ(cls.cfg)
        # cls.ws = workspaceService(cls.wsURL, token=token)
        # cls.ws = Workspace(cls.cfg['workspace-url'], token=cls.token)
        # cls.hs = HandleService(url=cls.cfg['handle-service-url'],
        #                        token=cls.token)
        cls.scratch = cls.cfg['scratch']
        shutil.rmtree(cls.scratch)
        os.mkdir(cls.scratch)
        suffix = int(time.time() * 1000)
        wsName = "test_kb_PRINSEQ_" + str(suffix)
        cls.ws_info = cls.wsClient.create_workspace({'workspace': wsName})
        cls.dfu = DataFileUtil(os.environ['SDK_CALLBACK_URL'], token=cls.token)
        cls.nodes_to_delete = []
        cls.nodes_to_delete.extend(cls.upload_test_reads())
        print("NODES TO DELETE: {}".format(str(cls.nodes_to_delete)))
        print('\n\n=============== Starting tests ==================')

    @classmethod
    def tearDownClass(cls):
        if cls.getWsName():
            cls.wsClient.delete_workspace({'workspace': cls.getWsName()})
            print(('Test workspace {} was deleted'.format(str(cls.getWsName()))))
        if hasattr(cls, 'nodes_to_delete'):
            for node in cls.nodes_to_delete:
                cls.delete_shock_node(node)

    def getWsClient(self):
        return self.__class__.wsClient

    @classmethod
    def getWsName(cls):
        return cls.ws_info[1]

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    @classmethod
    def upload_test_reads(cls):
        """
        Seeding an initial SE and PE Reads objects to test filtering
        """
        header = dict()
        header["Authorization"] = "Oauth {0}".format(cls.token)
        # readsUtils_Client = ReadsUtils(url=self.callback_url, token=ctx['token'])  # SDK local
        readsUtils_Client = ReadsUtils(os.environ['SDK_CALLBACK_URL'], token=cls.token)

        temp_nodes = []
        fwdtf = 'small_forward.fq'
        revtf = 'small_reverse.fq'
        fwdtarget = os.path.join(cls.scratch, fwdtf)
        revtarget = os.path.join(cls.scratch, revtf)
        print("CWD: "+str(os.getcwd()))
        shutil.copy('/kb/module/test/data/' + fwdtf, fwdtarget)
        shutil.copy('/kb/module/test/data/' + revtf, revtarget)

        # Upload single end reads
        cls.se_reads_reference = \
            readsUtils_Client.upload_reads({'wsname': cls.getWsName(),
                                            'name': "se_reads",
                                            'sequencing_tech': 'Illumina',
                                            'fwd_file': fwdtarget}
                                           )['obj_ref']

        se_data = cls.dfu.get_objects(
            {'object_refs': [cls.getWsName() + '/se_reads']})['data'][0]['data']

        temp_nodes.append(se_data['lib']['file']['id'])

        # Upload paired end reads
        cls.pe_reads_reference = \
            readsUtils_Client.upload_reads({'wsname': cls.getWsName(),
                                            'name': "pe_reads",
                                            'sequencing_tech': 'Illumina',
                                            'fwd_file': fwdtarget,
                                            'rev_file': revtarget,
                                            'insert_size_mean': 42,
                                            'insert_size_std_dev': 10,
                                            }
                                           )['obj_ref']
        pe_data = cls.dfu.get_objects(
            {'object_refs': [cls.getWsName() + '/pe_reads']})['data'][0]['data']
        temp_nodes.append(pe_data['lib1']['file']['id'])

        return temp_nodes

    @classmethod
    def delete_shock_node(cls, node_id):
        header = {'Authorization': 'Oauth {0}'.format(cls.token)}
        requests.delete(cls.shockURL + '/node/' + node_id, headers=header,
                        allow_redirects=True)
        print('Deleted shock node ' + node_id)

    @classmethod
    def getPeRef(cls):
        return cls.pe_reads_reference

    @classmethod
    def getSeRef(cls):
        print("READS REFERENCE:"+str(cls.se_reads_reference))
        return cls.se_reads_reference

    def test_invalid_threshold_value(self):
        output_reads_name = "SE_dust_2"
        lc_method = "dust"
        lc_threshold = 200
        exception = ValueError
        with self.assertRaises(exception) as context:
            self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref":
                                                             self.se_reads_reference,
                                                             "output_ws": self.getWsName(),
                                                             "output_reads_name": output_reads_name,
                                                             "lc_method": lc_method,
                                                             "lc_dust_threshold": lc_threshold})
            self.assertEqual(("The threshold for {} must be between 0 and 100, it is currently " +
                              "set to : {}").format(lc_method,
                                                    lc_threshold),
                             str(context.exception.message))

    def test_no_entropy_threshold(self):
        output_reads_name = "SE_entropy_2"
        lc_method = "entropy"
        lc_threshold = 200
        exception = ValueError
        with self.assertRaises(exception) as context:
            self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref":
                                                             self.se_reads_reference,
                                                             "output_ws": self.getWsName(),
                                                             "output_reads_name": output_reads_name,
                                                             "lc_method": lc_method,
                                                             "lc_dust_threshold": lc_threshold})
            self.assertEqual(("A low complexity threshold needs to be entered for " +
                              "{}").format(lc_method),
                             str(context.exception.message))

    def test_no_dust_threshold(self):
        # The original input reads file has 12500 reads. This filtered nearly 3000 reads.
        output_reads_name = "SE_dust_2"
        lc_method = "dust"
        lc_threshold = 200
        exception = ValueError
        with self.assertRaises(exception) as context:
            self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref":
                                                             self.se_reads_reference,
                                                             "output_ws": self.getWsName(),
                                                             "output_reads_name": output_reads_name,
                                                             "lc_method": lc_method,
                                                             "lc_entropy_threshold": lc_threshold})
            self.assertEqual(("A low complexity threshold needs to be entered for " +
                              "{}").format(lc_method),
                             str(context.exception.message))

    def test_se_dust_partial(self):
        # The original input reads file has 12500 reads. This filtered nearly 3000 reads.
        output_reads_name = "SE_dust_2"
        lc_method = "dust"
        lc_threshold = 2
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.se_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_dust_threshold": lc_threshold})
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 9544)
        self.assertEqual(reads_object['sequencing_tech'], "Illumina")
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)

    def test_se_dust_loose(self):
        # The original input reads file has 12500 reads. None of the reads get filtered.
        output_reads_name = "SE_dust_40"
        lc_method = "dust"
        lc_threshold = 40
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.se_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_dust_threshold": lc_threshold})
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 12500)
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)

    def test_se_entropy_partial(self):
        # The original input reads file has 12500 reads. Only 14 read gets filtered.
        output_reads_name = "SE_entropy_70"
        lc_method = "entropy"
        lc_threshold = 70
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.se_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_entropy_threshold": lc_threshold})
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 12486)
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)

    def test_se_entropy_loose(self):
        # The original input reads file has 12500 reads. No reads get filtered.
        output_reads_name = "SE_entropy_50"
        lc_method = "entropy"
        lc_threshold = 50
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.se_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_entropy_threshold": lc_threshold})
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 12500)
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)

    def test_se_entropy_none(self):
        # No New reads object created because all reads filtered out.
        output_reads_name = "SE_entropy_100"
        lc_method = "entropy"
        lc_threshold = 100

        self.getImpl().execReadLibraryPRINSEQ(self.ctx,
                                              {"input_reads_ref": self.se_reads_reference,
                                               "output_ws": self.getWsName(),
                                               "output_reads_name": output_reads_name,
                                               "lc_method": lc_method,
                                               "lc_entropy_threshold": lc_threshold})

        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + output_reads_name]})
        expected_error_prefix = f"No object with name {output_reads_name} exists in workspace"
        self.assertIn(expected_error_prefix, str(context.exception))

    def test_pe_dust_partial(self):
        # Three new objects made
        # 1) Filtered Pair-end object with matching good Reads
        # 2&3) Filtered FWD and REV Reads without matching pair (singletons).
        output_reads_name = "PE_dust_2"
        lc_method = "dust"
        lc_threshold = 2
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.pe_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_dust_threshold": lc_threshold})
        # Check for filtered paired reads object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 14950)
        self.assertEqual(reads_object['insert_size_mean'], 42)
        self.assertEqual(reads_object['sequencing_tech'], "Illumina")
        node = reads_object['lib1']['file']['id']
        self.delete_shock_node(node)
        # Check fwd singletons object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name +
                             "_fwd_singletons"]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 2069)
        self.assertEqual(reads_object['sequencing_tech'], "Illumina")
        self.assertTrue('insert_size_mean' not in reads_object)
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)
        # Check rev singletons object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name +
                             "_rev_singletons"]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 2002)
        self.assertEqual(reads_object['sequencing_tech'], "Illumina")
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)

    def test_pe_dust_strict(self):
        # Two new objects made (NO PAIRED END MADE as no matching pairs)
        # 1&2) Filtered FWD and REV Reads without matching pair (singletons).
        output_reads_name = "PE_dust_0"
        lc_method = "dust"
        lc_threshold = 0
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.pe_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_dust_threshold": lc_threshold})
        # Check filtered paired reads object does not exist
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + output_reads_name]})
        expected_error_prefix = f"No object with name {output_reads_name} exists in workspace"
        self.assertIn(expected_error_prefix, str(context.exception))
        # Check fwd singletons object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name +
                             "_fwd_singletons"]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 1)
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)
        # Check rev singletons object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name +
                             "_rev_singletons"]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 1)
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)

    def test_pe_dust_loose(self):
        # Only 1 new objects made since no reads filtered.
        # 1) Filtered Pair-end object with matching Reads
        output_reads_name = "PE_dust_100"
        lc_method = "dust"
        lc_threshold = 100
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.pe_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_dust_threshold": lc_threshold})
        # Check for filtered paired reads object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 25000)
        node = reads_object['lib1']['file']['id']
        self.delete_shock_node(node)
        # Check fwd singletons object does not exist
        temp_object_name = output_reads_name + "_fwd_singletons"
        expected_error_prefix = f"No object with name {temp_object_name} exists in workspace"
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + temp_object_name]})
        self.assertIn(expected_error_prefix, str(context.exception))
        # Check rev singletons object does not exist
        temp_object_name = output_reads_name + "_rev_singletons"
        expected_error_prefix = f"No object with name {temp_object_name} exists in workspace"
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + temp_object_name]})
        # print "ERROR:{}:".format(str(context.exception.message))
        # expected_error_prefix = \
        #    "No object with name {} exists in workspace".format(temp_object_name)
        self.assertIn(expected_error_prefix, str(context.exception))

    def test_pe_entropy_partial(self):
        # Two new objects made (the reverse singleton has no reads, no object made)
        # 1) Filtered Pair-end object with matching good Reads
        # 2) Filtered FWD and REV Reads without matching pair (singletons).
        output_reads_name = "PE_entropy_60"
        lc_method = "entropy"
        lc_threshold = 60
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.pe_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_entropy_threshold": lc_threshold})
        # Check for filtered paired reads object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 24996)
        node = reads_object['lib1']['file']['id']
        self.delete_shock_node(node)
        # Check fwd singletons object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name +
                             "_fwd_singletons"]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 2)
        node = reads_object['lib']['file']['id']
        self.delete_shock_node(node)
        # Check rev singletons object does not exist
        temp_object_name = output_reads_name + "_rev_singletons"
        expected_error_prefix = f"No object with name {temp_object_name} exists in workspace"
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + temp_object_name]})
        self.assertIn(expected_error_prefix, str(context.exception))

    def test_pe_entropy_strict(self):
        # No new objects made
        output_reads_name = "PE_entropy_100"
        lc_method = "entropy"
        lc_threshold = 100
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.pe_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_entropy_threshold": lc_threshold})
        # Check filtered paired reads object does not exist
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + output_reads_name]})
        expected_error_prefix = f"No object with name {output_reads_name} exists in workspace"
        self.assertIn(expected_error_prefix, str(context.exception))
        # Check fwd singletons object does not exist
        temp_object_name = output_reads_name + "_fwd_singletons"
        expected_error_prefix = f"No object with name {temp_object_name} exists in workspace"
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + temp_object_name]})
        self.assertIn(expected_error_prefix, str(context.exception))
        # Check rev singletons object does not exist
        temp_object_name = output_reads_name + "_rev_singletons"
        expected_error_prefix = f"No object with name {temp_object_name} exists in workspace"
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + temp_object_name]})
        self.assertIn(expected_error_prefix, str(context.exception))

    def test_pe_entropy_loose(self):
        # Only 1 new objects made since no reads filtered.
        # 1) Filtered Pair-end object with matching Reads
        output_reads_name = "PE_entropy_0"
        lc_method = "entropy"
        lc_threshold = 0
        self.getImpl().execReadLibraryPRINSEQ(self.ctx, {"input_reads_ref": self.pe_reads_reference,
                                                         "output_ws": self.getWsName(),
                                                         "output_reads_name": output_reads_name,
                                                         "lc_method": lc_method,
                                                         "lc_entropy_threshold": lc_threshold})
        # Check for filtered paired reads object
        reads_object = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/' + output_reads_name]})['data'][0]['data']
        self.assertEqual(reads_object['read_count'], 25000)
        node = reads_object['lib1']['file']['id']
        self.delete_shock_node(node)
        # Check fwd singletons object does not exist
        temp_object_name = output_reads_name + "_fwd_singletons"
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + temp_object_name]})
        expected_error_prefix = f"No object with name {temp_object_name} exists in workspace"
        self.assertIn(expected_error_prefix, str(context.exception))
        # Check rev singletons object does not exist
        temp_object_name = output_reads_name + "_rev_singletons"
        with self.assertRaises(DFUError) as context:
            self.dfu.get_objects(
                {'object_refs': [self.getWsName() + '/' + temp_object_name]})
        expected_error_prefix = f"No object with name {temp_object_name} exists in workspace"
        self.assertIn(expected_error_prefix, str(context.exception))
