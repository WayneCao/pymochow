# Copyright 2023 Baidu, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file
# except in compliance with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the
# License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
# either express or implied. See the License for the specific language governing permissions
# and limitations under the License.

"""
Examples for mochow client
"""

import time
import json
import random

import pymochow
import logging
from pymochow.configuration import Configuration
from pymochow.auth.bce_credentials import BceCredentials
from pymochow.exception import ClientError, ServerError
from pymochow.model.schema import (
    Schema,
    Field,
    SecondaryIndex,
    FilteringIndex,
    VectorIndex,
    HNSWParams,
    HNSWPQParams,
    PUCKParams,
    AutoBuildTiming,
    InvertedIndex,
    InvertedIndexParams,
    RRFRank,
    WeightedRank,
)
from pymochow.model.enum import (
    FieldType, ElementType, IndexType, InvertedIndexAnalyzer, InvertedIndexParseMode, MetricType, ServerErrCode,
    InvertedIndexFieldAttribute
)
from pymochow.model.enum import TableState, IndexState
from pymochow.model.table import (
    Partition,
    Row,
    FloatVector,
    BinaryVector,
    SparseFloatVector,
    BatchQueryKey,
    VectorSearchConfig,
    VectorTopkSearchRequest,
    VectorRangeSearchRequest,
    VectorBatchSearchRequest,
    MultiVectorSearchRequest,
    BM25SearchRequest,
    HybridSearchRequest,
)

logging.basicConfig(filename='example.log', level=logging.DEBUG,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestMochow:
    def __init__(self, config, vector_index_type):
        """
        init mochow client
        """
        self._client = pymochow.MochowClient(config)
        self._vector_index_type = vector_index_type
    
    def clear(self):
        db = None
        try:
            db = self._client.database('book')
        except ClientError as e:
            logger.debug("database {} not found.".format('book'))
            pass
        
        if db is not None:
            try:
                db.drop_table('book_segments')
            except ServerError as e:
                logger.debug("drop table error {}".format(e))
                if e.code == ServerErrCode.TABLE_NOT_EXIST:
                    pass
            time.sleep(10)
            db.drop_database()

    def create_db_and_table(self):
        """create database&table"""
        database = 'book'
        table_name = 'book_segments'

        db = self._client.create_database(database)

        database_list = self._client.list_databases()
        for db_item in database_list:
            logger.debug("database: {}".format(db_item.database_name))
        
        fields = []
        fields.append(Field("id", FieldType.STRING, primary_key=True,
            partition_key=True, auto_increment=False, not_null=True))
        fields.append(Field("bookName", FieldType.STRING, not_null=True))
        fields.append(Field("author", FieldType.STRING))
        fields.append(Field("page", FieldType.UINT32))
        fields.append(Field("segment", FieldType.TEXT))
        fields.append(Field("vector", FieldType.FLOAT_VECTOR, not_null=True, dimension=4))
        # 'element_type' must be set for ARRAY, 'max_capacity' is optional
        fields.append(Field("arr_field", FieldType.ARRAY, element_type=ElementType.STRING, not_null=True))
        fields.append(Field("json_field", FieldType.JSON))
        indexes = []

        if self._vector_index_type == IndexType.HNSW:
            indexes.append(VectorIndex(index_name="vector_idx", index_type=IndexType.HNSW,
            field="vector", metric_type=MetricType.L2, 
            params=HNSWParams(m=32, efconstruction=200)))
        elif self._vector_index_type == IndexType.HNSWPQ:
            indexes.append(VectorIndex(index_name="vector_idx", index_type=IndexType.HNSWPQ,
            field="vector", metric_type=MetricType.L2, 
            params=HNSWPQParams(m=16, efconstruction=200, NSQ=4, samplerate=1.0)))
        elif self._vector_index_type == IndexType.PUCK:
            indexes.append(VectorIndex(index_name="vector_idx", index_type=IndexType.PUCK,
            field="vector", metric_type=MetricType.L2, 
            params=PUCKParams(coarseClusterCount=5, fineClusterCount=5)))
        else:
            raise Exception("not support index type")

        indexes.append(SecondaryIndex(index_name="book_name_idx", field="bookName"))
        indexes.append(FilteringIndex(index_name="book_name_filtering_idx", fields=["bookName"]))
        indexes.append(InvertedIndex(index_name="book_segment_inverted_idx",
                               fields=["segment"],
                               params=InvertedIndexParams(analyzer=InvertedIndexAnalyzer.CHINESE_ANALYZER,
                                                          parse_mode=InvertedIndexParseMode.COARSE_MODE,
                                                          case_sensitive=True),
                               field_attributes=[InvertedIndexFieldAttribute.ANALYZED]))
        db.create_table(
            table_name=table_name,
            replication=3,
            partition=Partition(partition_num=1),
            schema=Schema(fields=fields, indexes=indexes)
        )

        while True:
            time.sleep(2)
            table = db.describe_table(table_name)
            if table.state == TableState.NORMAL:
                break
        
        time.sleep(10)
        logger.debug("table: {}".format(table.to_dict()))

        db.modify_table(table_name, datanode_memory_reserved_in_gb=0.1)
        time.sleep(10)
        logger.debug("table: {}".format(table.to_dict()))

    def upsert_data(self):
        """upsert data"""
        db = self._client.database('book')
        table = db.table('book_segments')

        rows = [
            Row(id='0001',
                vector=[1, 0.21, 0.213, 0],
                bookName='西游记',
                author='吴承恩',
                page=21,
                arr_field=[],
                json_field={},
                segment='富贵功名，前缘分定，为人切莫欺心。'),
            Row(id='0002',
                vector=[2, 0.22, 0.213, 0],
                bookName='西游记',
                author='吴承恩',
                page=22,
                arr_field=[],
                json_field={"page": 22},
                segment='正大光明，忠良善果弥深。些些狂妄天加谴，眼前不遇待时临。'),
            Row(id='0003',
                vector=[3, 0.23, 0.213, 0],
                bookName='三国演义',
                author='罗贯中',
                page=23,
                arr_field=["细作", "吕布"],
                json_field={"author": "罗贯中"},
                segment='细作探知这个消息，飞报吕布。'),
            Row(id='0004',
                vector=[4, 0.24, 0.213, 0],
                bookName='三国演义',
                author='罗贯中',
                page=24,
                arr_field=["吕布", "陈宫", "刘玄德"],
                json_field={"bookName": "三国演义"},
                segment='布大惊，与陈宫商议。宫曰：“闻刘玄德新领徐州，可往投之。”' \
                        '布从其言，竟投徐州来。有人报知玄德。'),
            Row(id='0005',
                vector=[5, 0.25, 0.213, 0],
                bookName='三国演义',
                author='罗贯中',
                page=25,
                arr_field=["玄德", "糜竺", "吕布"],
                json_field={
                    "product_info": {
                        "category": "electronics",
                        "brand": "BrandA"
                    },
                    "price": 99.99,
                    "in_stock": True,
                    "tags": ["summer_sale", "clearance"]
                },
                segment='玄德曰：“布乃当今英勇之士，可出迎之。”' \
                '糜竺曰：“吕布乃虎狼之徒，不可收留；收则伤人矣。'),
        ]
        
        i = 6
        while i <= 100:
            rows.append(Row(id=str(i),
                vector=[i, 0.2 + i * 0.01, 0.213, 0],
                bookName='三国演义',
                author='罗贯中',
                page=25,
                arr_field=["玄德", "糜竺", "吕布"],
                segment='玄德曰：“布乃当今英勇之士，可出迎之。”' \
                '糜竺曰：“吕布乃虎狼之徒，不可收留；收则伤人矣。'))
            i += 1

        table.upsert(rows=rows)
        time.sleep(10)

    def change_table_schema(self):
        """change table schema"""
        db = self._client.database('book')
        table = db.table('book_segments')
        fields = []
        fields.append(Field("publisher", FieldType.STRING))
        fields.append(Field("synopsis", FieldType.STRING))

        res = table.add_fields(schema=Schema(fields=fields))
        logger.debug("res: {}".format(res))

    def show_table_stats(self):
        """show table stats"""
        db = self._client.database('book')
        table = db.table('book_segments')

        res = table.stats()
        logger.debug("res: {}".format(res))

    def query_data(self):
        """query data"""
        db = self._client.database('book')
        table = db.table('book_segments')

        primary_key = {'id':'0001'}
        projections = ["id", "bookName"]
        res = table.query(primary_key=primary_key, projections=projections, 
                retrieve_vector=True)
        logger.debug("query res: {}".format(res))

    def batch_query_data(self):
        """query data"""
        db = self._client.database('book')
        table = db.table('book_segments')
        projections = ["id", "bookName"]
        res = table.batch_query(keys=[BatchQueryKey({'id': '0001'}),
                                      BatchQueryKey({'id': '0002'}),
                                      BatchQueryKey({'id': '1003'})],
                                projections=projections,
                                retrieve_vector=True)
        logger.debug("batch query res: {}".format(res))

    def vector_search(self):
        """search data"""
        db = self._client.database('book')
        table = db.table('book_segments')

        table.rebuild_index("vector_idx")
        while True:
            time.sleep(2)
            index = table.describe_index("vector_idx")
            if index.state == IndexState.NORMAL:
                break

        # single topk search
        if self._vector_index_type == IndexType.HNSW or self._vector_index_type == IndexType.HNSWPQ:
            request = VectorTopkSearchRequest(vector_field="vector", vector=FloatVector([1, 0.21, 0.213, 0]),
                                              limit=10, filter="bookName='三国演义'",
                                              config=VectorSearchConfig(ef=200))
        elif self._vector_index_type == IndexType.PUCK:
            request = VectorTopkSearchRequest(vector_field="vector", vector=FloatVector([1, 0.21, 0.213, 0]),
                                              limit=5, filter="bookName='三国演义'",
                                              config=VectorSearchConfig(search_coarse_count=5))
        res = table.vector_search(request=request)
        logger.debug("topk search res: {}".format(res))

        # single range search
        if self._vector_index_type == IndexType.HNSW or self._vector_index_type == IndexType.HNSWPQ:
            request = VectorRangeSearchRequest(vector_field="vector", vector=FloatVector([1, 0.21, 0.213, 0]),
                                               distance_range=(0, 20), limit=10,
                                               filter="bookName='三国演义'",
                                               config=VectorSearchConfig(ef=200))
        elif self._vector_index_type == IndexType.PUCK:
            request = VectorRangeSearchRequest(vector_field="vector", vector=FloatVector([1, 0.21, 0.213, 0]),
                                               distance_range=(0, 20), limit=5,
                                               config=VectorSearchConfig(search_coarse_count=5))
        res = table.vector_search(request=request)
        logger.debug("range search res: {}".format(res))

        # batch search
        if self._vector_index_type == IndexType.HNSW or self._vector_index_type == IndexType.HNSWPQ:
            request = VectorBatchSearchRequest(vector_field="vector",
                                               vectors=[FloatVector([1, 0.21, 0.213, 0]),
                                                        FloatVector([1, 0.32, 0.513, 0])],
                                               limit=10, filter="bookName='三国演义'",
                                               config=VectorSearchConfig(ef=200))
        elif self._vector_index_type == IndexType.PUCK:
            request = VectorBatchSearchRequest(vector_field="vector",
                                               vectors=[FloatVector([1, 0.21, 0.213, 0]),
                                                        FloatVector([1, 0.32, 0.513, 0])],
                                               limit=5, filter="bookName='三国演义'",
                                               config=VectorSearchConfig(search_coarse_count=5))
        res = table.vector_search(request=request)
        logger.debug("batch search res: {}".format(res))

        # multi-vector search
        if self._vector_index_type == IndexType.HNSW or self._vector_index_type == IndexType.HNSWPQ:
            config=VectorSearchConfig(ef=200)
        elif self._vector_index_type == IndexType.PUCK:
            config=VectorSearchConfig(search_coarse_count=5)

        # in real world senario, you should use vectors in different vector fields
        requests = [
            VectorTopkSearchRequest(vector_field="vector",
                                    vector=FloatVector([1, 0.21, 0.213, 0]),
                                    limit=10,
                                    config=config),
            VectorTopkSearchRequest(vector_field="vector",
                                    vector=FloatVector([1, 0.21, 0.213, 0]),
                                    limit=10,
                                    config=config)
        ]
        request = MultiVectorSearchRequest(requests=requests,
                                           ranking=RRFRank(60),
                                           limit=10, filter="bookName='三国演义'")

        res = table.vector_search(request=request, projections=["id"])
        logger.debug("multi vector search res: {}".format(res))

    def search_iterator(self):
        """search iterator"""
        db = self._client.database('book')
        table = db.table('book_segments')

        # Example1: search iterator for TopK search.
        logger.debug("Start search iterator for TopK search")
        request = VectorTopkSearchRequest(vector_field="vector", vector=FloatVector([1, 0.21, 0.213, 0]),
                                          limit=1000, config=VectorSearchConfig(ef=2000))

        iterator1 = table.search_iterator(request=request, batch_size=1000, total_size=10000)
        while True:
            rows = iterator1.next()
            if not rows:
                break
            logger.debug("rows:{}".format(rows))
        iterator1.close()
        logger.debug("Finish search iterator for TopK search")

        # Example2: search iterator for multi-vector search.
        logger.debug("Start search iterator for multi-vector search")
        requests = [
            VectorTopkSearchRequest(vector_field="vector",
                                    vector=FloatVector([1, 0.21, 0.213, 0]),
                                    limit=1000,
                                    config=VectorSearchConfig(ef=2000)),
            VectorTopkSearchRequest(vector_field="vector",
                                    vector=FloatVector([1, 0.21, 0.213, 0]),
                                    limit=1000,
                                    config=VectorSearchConfig(ef=2000))
        ]
        request = MultiVectorSearchRequest(requests=requests,
                                           ranking=WeightedRank([1.0, 1.0]),
                                           limit=1000)

        iterator2 = table.search_iterator(request=request, batch_size=1000, total_size=10000)
        while True:
            rows = iterator2.next()
            if not rows:
                break
            logger.debug("rows:{}".format(rows))
        iterator2.close()
        logger.debug("Finish search iterator for multi-vector search")

    def bm25_search(self):
        """bm25 search"""
        db = self._client.database('book')
        table = db.table('book_segments')

        request = BM25SearchRequest(index_name="book_segment_inverted_idx",
                                    search_text="吕布",
                                    limit=10,
                                    filter="bookName='三国演义'")
        res = table.bm25_search(request=request)
        logger.debug("BM25 search res: {}".format(res))

    def hybrid_search(self):
        """do anns and/or bm25 search"""
        db = self._client.database('book')
        table = db.table('book_segments')

        if self._vector_index_type == IndexType.HNSW or self._vector_index_type == IndexType.HNSWPQ:
            config = VectorSearchConfig(ef=200)
        elif self._vector_index_type == IndexType.PUCK:
            config = VectorSearchConfig(search_coarse_count=5)
        vector_request = VectorTopkSearchRequest(vector_field="vector",
                                                 vector=FloatVector([1, 0.21, 0.213, 0]),
                                                 limit=None,
                                                 config=config)
        bm25_request = BM25SearchRequest(index_name="book_segment_inverted_idx",
                                         search_text="吕布")
        hybrid_request = HybridSearchRequest(vector_request=vector_request,
                                             vector_weight=0.4,
                                             bm25_request=bm25_request,
                                             bm25_weight=0.6,
                                             filter="bookName='三国演义'",
                                             limit=15)

        res = table.hybrid_search(request=hybrid_request)

        logger.debug("hybrid search res: {}".format(res))

    def select_data(self):
        """select data"""
        db = self._client.database('book')
        table = db.table('book_segments')
        projections = ["id", "bookName", "json_field"]

        select_finished = False
        marker = None
        while True:
            res = table.select(marker=marker, projections=projections, limit=20)
            logger.debug("res: {}".format(res))
            if res.is_truncated is False:
                logger.debug("select finished")
                break
            else:
                logger.debug("select next batch")
                marker = res.next_marker

    def update_data(self):
        """update data"""
        db = self._client.database('book')
        table = db.table('book_segments')

        primary_key = {'id': '0001'}
        update_fields = {'bookName': '红楼梦',
                         'author': '曹雪芹',
                         'page': 21,
                         'segment': '满纸荒唐言，一把辛酸泪'}
        res = table.update(primary_key=primary_key, update_fields=update_fields)
        logger.debug("res: {}".format(res))

    def delete_data(self):
        """delete data"""
        db = self._client.database('book')
        table = db.table('book_segments')

        primary_key = {'id': '0001'}
        res = table.delete(primary_key=primary_key)
        logger.debug("res: {}".format(res))

    def drop_and_create_vindex(self):
        """drop and create vindex"""
        db = self._client.database('book')
        table = db.table('book_segments')
        table.drop_index("vector_idx")
        while True:
            time.sleep(2)
            try:
                index = table.describe_index("vector_idx")
            except ServerError as e:
                logger.debug("code: {}".format(e.code))
                if e.code == ServerErrCode.INDEX_NOT_EXIST:
                    break
        
        indexes = []
        if self._vector_index_type == IndexType.HNSW:
            indexes.append(VectorIndex(index_name="vector_idx", index_type=IndexType.HNSW,
            field="vector", metric_type=MetricType.L2, 
            params=HNSWParams(m=16, efconstruction=200), auto_build=False))
        elif self._vector_index_type == IndexType.HNSWPQ:
            indexes.append(VectorIndex(index_name="vector_idx", index_type=IndexType.HNSWPQ,
            field="vector", metric_type=MetricType.L2, 
            params=HNSWPQParams(m=16, efconstruction=200, NSQ=4, samplerate=1.0)))
        elif self._vector_index_type == IndexType.PUCK:
            indexes.append(VectorIndex(index_name="vector_idx", index_type=IndexType.PUCK,
            field="vector", metric_type=MetricType.L2, 
            params=PUCKParams(coarseClusterCount=5, fineClusterCount=5), auto_build=False))
        else:
            raise Exception("not support index type")
        table.create_indexes(indexes)
        time.sleep(1)
        table.modify_index(index_name="vector_idx", auto_build=True, 
                        auto_build_index_policy=AutoBuildTiming("2024-01-01 00:00:00"))
        index = table.describe_index("vector_idx")
        logger.debug("index: {}".format(index.to_dict()))

    def delete_and_drop(self):
        """delete and drop"""
        db = self._client.database('book')

        db.drop_table('book_segments')
        time.sleep(10)

        db.drop_database()
        self._client.close()

    def binary_vector_usage_example(self):
        # convert num to it's binary representation, a list of 0 and 1
        def num_to_binary_list(num, dimension):
            binary_str = bin(num)[2:]
            binary_list = [int(bit) for bit in binary_str]
            if len(binary_list) > dimension:
                binary_list = binary_list[:dimension]
            elif len(binary_list) < dimension:
                tmp = [0] * (dimension - len(binary_list))
                tmp.extend(binary_list)
                binary_list = tmp
            assert(len(binary_list) == dimension)
            return binary_list

        # 1. create table
        database = "test_binary_vec"
        table_name = "test_binary_vec_tab"

        db = None
        try:
            db = self._client.database(database)
        except ClientError:
            pass
        if db is not None:
            try:
                db.drop_table(table_name)
            except ServerError:
                pass
            time.sleep(10)
            db.drop_database()

        db = self._client.create_database(database)
        vector_dimension = 128
        fields = []
        fields.append(Field("id", FieldType.STRING, primary_key=True,
                      partition_key=True, auto_increment=False, not_null=True))
        fields.append(Field("vector", FieldType.BINARY_VECTOR, not_null=True, dimension=vector_dimension))
        db.create_table(table_name=table_name, replication=3, partition=Partition(
            partition_num=1), schema=Schema(fields=fields))
        while True:
            time.sleep(2)
            if db.describe_table(table_name).state == TableState.NORMAL:
                break

        # 2. insert to table
        table = db.table(table_name)
        rows = []
        for num in range(50):
            vec = BinaryVector.from_binary_list(num_to_binary_list(num, vector_dimension))
            rows.append(Row(id=str(num), vector=vec))
        table.upsert(rows=rows)

        # 3. search binary vector
        target = BinaryVector.from_binary_list(num_to_binary_list(123, vector_dimension))
        request = VectorTopkSearchRequest(vector_field="vector", vector=target, limit=10)
        res = table.vector_search(request=request)
        logger.debug("res: {}".format(res))

    def sparse_vector_usage_example(self):
        # 1. create table
        database = "test_sparse_vec"
        table_name = "test_sparse_vec_tab"

        db = None
        try:
            db = self._client.database(database)
        except ClientError:
            pass
        if db is not None:
            try:
                db.drop_table(table_name)
            except ServerError:
                pass
            time.sleep(10)
            db.drop_database()

        db = self._client.create_database(database)
        fields = []
        fields.append(Field("id", FieldType.STRING, primary_key=True,
                            partition_key=True, auto_increment=False, not_null=True))
        fields.append(Field("vector", FieldType.SPARSE_FLOAT_VECTOR, not_null=True))

        indexes = []
        indexes.append(VectorIndex(index_name="sparse_vector_idx",
                                   index_type=IndexType.SPARSE_OPTIMIZED_FLAT,
                                   field="vector",
                                   metric_type=MetricType.IP))

        db.create_table(table_name=table_name, replication=3,
                        partition=Partition(partition_num=1),
                        schema=Schema(fields=fields, indexes=indexes))
        while True:
            time.sleep(2)
            if db.describe_table(table_name).state == TableState.NORMAL:
                break

        # 2. insert to table
        rows = []
        table = db.table(table_name)
        for num in range(50):
            vec = SparseFloatVector.from_dict({1: 0.56465, 100: 0.2366456, 10000: 0.543111})
            rows.append(Row(id=str(num), vector=vec))
        table.upsert(rows=rows)

        # 3. search binary vector
        target = SparseFloatVector.from_dict({1: 0.56465, 100: 0.2366456, 10000: 0.543111})
        request = VectorTopkSearchRequest(vector_field="vector", vector=target, limit=10)
        res = table.vector_search(request=request)
        logger.debug("res: {}".format(res))


if __name__ == "__main__":
    account = 'root'
    api_key = '********'
    endpoint = 'http://*.*.*.*:*' #example:http://127.0.0.1:8511

    config = Configuration(credentials=BceCredentials(account, api_key),
            endpoint=endpoint)
    test_vdb = TestMochow(config, IndexType.HNSWPQ)
    test_vdb.clear()
    test_vdb.create_db_and_table()
    test_vdb.upsert_data()
    test_vdb.select_data()
    test_vdb.change_table_schema()
    test_vdb.show_table_stats()
    test_vdb.query_data()
    test_vdb.batch_query_data()
    test_vdb.vector_search()
    test_vdb.search_iterator()
    test_vdb.bm25_search()
    test_vdb.hybrid_search()
    test_vdb.update_data()
    test_vdb.delete_data()
    test_vdb.drop_and_create_vindex()
    test_vdb.binary_vector_usage_example()
    test_vdb.sparse_vector_usage_example()
    test_vdb.delete_and_drop()

