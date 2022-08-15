from base64 import b64encode, b64decode

from bson.objectid import ObjectId
from bson.binary import Binary
from pydantic import BaseModel, Field


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class PyBinary(Binary):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        try:
            return Binary(b64decode(v))
        except:
            raise ValueError("Invalid binary")

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

    def __str__(self) -> str:
        return b64encode(super()).decode("utf-8")

    def __repr__(self):
        return f'PyBinary({super().__repr__()})'


class DefaultModel(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str, PyBinary: str}
