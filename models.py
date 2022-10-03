# manadtory for forward declaration of types. 
# see here: https://docs.python.org/3/library/__future__.html
from __future__ import annotations
import contextlib
import copy
from dataclasses import asdict, dataclass, field
import logging
import importlib
from bson import ObjectId
from typing import Any, Dict, List, Optional, Union
from pymongo import MongoClient
from gridfs import GridFS
from pymongo.collection import Collection
from pymongo.results import UpdateResult, InsertOneResult, DeleteResult
from pymongo.database import Database

# # open file
# file = open('d:/file.jpg')
 
# # get the cursor positioned at end
# file.seek(0, os.SEEK_END)
 
# # get the current position of cursor
# # this will be equivalent to size of file
# print("Size of file is :", file.tell(), "bytes")

#TODO check byte objects to be compliant with mongo db file size limit of 16MB

def find_pytype(full_name:str) -> object:
    arr : List[str] = full_name.rsplit(".", maxsplit=1)
    return _find_pytype(arr[0], arr[1])

def _find_pytype(module_name:str, class_name:str) -> object:
    try:
        module_ = importlib.import_module(module_name)
        try:
            class_ = getattr(module_, class_name)
        except AttributeError:
            logging.error('Class does not exist')
    except ImportError:
        logging.error('Module does not exist')
    return class_

global _db_connection
_db_connection = None
@contextlib.contextmanager
def mongodb_connection(database_server: str, database_name: str):
    with MongoClient(database_server) as client:
        try:
            info = client.server_info() # just for testing the connection
            global _db_connection
            _old = _db_connection
            _db_connection = client[database_name]
            yield client
        finally:
            _db_connection = _old
            client.close()

@dataclass()
class DBserializable():
    """
    Base for all classes that are to be persisted in a database.
    Do not adjust _pytype, it is automated.
    """
    _pytype: str =  __module__  + "." +__qualname__

    def __post_init__(self):
        self._pytype = self.__class__.__module__  + "." + self.__class__.__qualname__
        pass 

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def new(cls, dict:Dict[str, Any]) -> DBserializable:
        instanceOfcls = cls()
        instanceOfcls.from_dict(dict)
        return instanceOfcls

    def from_dict(self, dict: Dict[str, Any]) -> None:
        new_dict = copy.deepcopy(dict)
        for key, v in dict.items():
            if isinstance(v, Dict):
                if "_pytype" in v:
                    logging.debug("instance class from string: {}".format(v["_pytype"]))
                    clsx = find_pytype(v["_pytype"])
                    cls = clsx(**v)
                    new_dict[key] = cls
        self.__init__(**new_dict)
        pass

@dataclass
class MongoDBEntry(DBserializable):
    """
    Base for all classes that own their own collection.
    Implements standard CRUD-functions, depends on a valid Database connection which can be created with:
    
    with mongodb_connection(database_server, database_name) as client:
        .... use classes

    How to create a new Dataclass:
    @dataclass
    class Clazz(MongoDBEntry, collection="mycollection"):
        name : Optional[str] = None

    """
    def __init_subclass__(cls, collection: Collection, **kwargs) -> None:
        cls.collection = collection
        return super().__init_subclass__(**kwargs)

    _id : Optional[ObjectId] = None

    def _check_db_connection(db_connection:Database):
        if db_connection is None:
            db_connection = _db_connection 
        if db_connection is None:
            raise ConnectionError("No database connection present")
        return db_connection

    @classmethod 
    def find_all(cls, pattern={}, projection={}, db: Database=None):
        db = MongoDBEntry._check_db_connection(db)
        try: 
            with db.client.start_session() as session:
                cursor = db[cls.collection].find(pattern, projection, no_cursor_timeout=True, session=session)
                for col_entry in cursor:
                    yield cls.new(col_entry)
                     # we have large collections, so interating over it might take some time => refresh
                    db.client.admin.command('refreshSessions', [session.session_id], session=session)
        finally:
            cursor.close()

    def save(self, db: Database=None) -> Union[UpdateResult, InsertOneResult]:
        return self.insert(db) if self._id is None else self.update(db)        

    def update(self, db: Database=None) -> UpdateResult:
        db = MongoDBEntry._check_db_connection(db)
        res = db[self.collection].update_one({"_id":self._id}, {"$set": self.to_dict()})
        return res

    def insert(self, db: Database=None) -> InsertOneResult:
        db = MongoDBEntry._check_db_connection(db)
        res = db[self.collection].insert_one(self.to_dict())
        setattr(self, "_id", ObjectId(res.inserted_id))
        return res

    def delete(self, db: Database=None) -> DeleteResult:
        db = MongoDBEntry._check_db_connection(db)
        res = db[self.collection].delete_one({"_id":self._id})
        return res
    
    @classmethod
    def find_one(cls, pattern={}, db: Database=None) -> Union[MongoDBEntry, None]:
        db = MongoDBEntry._check_db_connection(db)
        dict = db[cls.collection].find_one(pattern)
        if dict is not None:
            clazz = find_pytype(dict["_pytype"])
            return clazz.new(dict)
        else:
             return None

    @classmethod
    def find_by_id(cls, id: str, db: Database=None) -> Union[MongoDBEntry, None]:
        return cls.find_one({"_id": ObjectId(id)}, db)

    @classmethod
    def find_by_obj_id(cls, id: ObjectId, db: Database=None) -> Union[MongoDBEntry, None]:
        return cls.find_one({"_id": id}, db)

    @classmethod
    def create_index(cls, db: Database=None, **kwargs):
        db = MongoDBEntry._check_db_connection(db)
        db[cls.collection].create_index(**kwargs)
        pass

    @classmethod
    def index_information(cls, db: Database=None):
        db = MongoDBEntry._check_db_connection(db)
        return db[cls.collection].index_information()
        
@dataclass
class Source(DBserializable):
    local_titel : str = ""
    html : bytes = field(default_factory=bytes)
    content : Dict[str, Any] = field(default_factory=dict)
    failed_requests: List[str] = field(default_factory=list)
    #iframes : List[Source] = field(default_factory=dict)

@dataclass
class Analysis(MongoDBEntry, collection="analyses"):
    data : Dict[str, Any] = field(default_factory=dict)
    
@dataclass
class Webelement(MongoDBEntry, collection= "webelement"):
    name : str = ""
    screenshot : bytes = field(default_factory=bytes)
    webpage_id : Optional[ObjectId] = None 
    # html fragment, coresponding css and images 
    html : bytes = field(default_factory=bytes)
    css : bytes = field(default_factory=bytes)
    other : Dict[str, Any] = field(default_factory=dict)
    analysis_id : Optional[ObjectId] = None

@dataclass
class Reference(MongoDBEntry, collection="references"):
    store_name: str = ""
    store_url: str = ""
    titel : str = ""
    demo_url : Optional[str] = ""
    description : Optional[str] = ""
    description_orgiginal : Optional[str] = ""
    title_img_bytes : Optional[bytes] = field(default_factory=bytes)
    tags : List[str] = field(default_factory=list)
    additional_info : List[str] = field(default_factory=list)
    similar_templates : List[str] = field(default_factory=list)

@dataclass
class Webpage(MongoDBEntry, collection="webpages"):
    url: str = ""
    titel :str = ""
    source: Optional[Source] = None
    screenshots: Dict[str, ObjectId] = field(default_factory=dict)
    webelements: Dict[str, ObjectId] = field(default_factory=dict)
    zip : Optional[Any] = None
    """
    screenshot_hd_bytes : bytes = field(default_factory=bytes)
    screenshot_extended_bytes : bytes = field(default_factory=bytes)
    screenshot_body_bytes : bytes = field(default_factory=bytes)
    #screenshot_portrait_b64 : str = ""
    #screenshot_mobile:b64 : str = ""
    """
    reference_id : Optional[ObjectId] = None
    analysis_id : Optional[ObjectId] = None
    ismobile: bool = False

def test_serialization():
    p = Webpage()
    p2 = Webpage.new(p.to_dict())
    c = p.to_dict()
    print("json serialization test: ", "success" if str(p.__repr__()) == str(p2.__repr__()) and p == p2 else "failure")

def test_mongo_serialization():
    from pymongo import mongo_client
    client = mongo_client.MongoClient("mongodb://localhost:27017/")
    db = client["webdesign"]
    import models
    p = models.Webpage()
    id = db["webpages"].insert_one(p.to_dict()).inserted_id
    setattr(p, "_id", ObjectId(id))

    find = db["webpages"].find_one({"_id": ObjectId(id)})
    p2 = models.Webpage.new(find)
    res = Webpage.find(id, db)
    res3 = p2.find(id, db)
    delete_info = res.delete(db)
    #o = db["webpages"].delete_one({"_id": ObjectId(id)})
    print("Mongo serialization test: ", "success" if p == p2 else "failure")

if __name__ == "__main__":
    #test_serialization()
    #test_mongo_serialization()
    with mongodb_connection("mongodb://localhost:27017/", "webdesign") as client:
        db = client["test"]
        fs = GridFS(db)

        # note filename has to unique
        file_id = fs.put(b"byte data", filename="test.txt")
        print(file_id)
        # page = Webpage()
        # page.screenshots.update({"<name>": file_id})