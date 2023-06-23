from dataclasses import dataclass
from datetime import (
    date,
    datetime,
    timezone,
    timedelta,
)
from json import dumps, loads
from typing import List, Tuple, TypedDict
from uuid import UUID
from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)
from phonenumbers import PhoneNumber

import pytest
from schemander import (
    Date,
    DateTime,
    Email,
    IANATimeZone,
    InternalObjectTypeString,
    JWTToken,
    MetaSchema,
    Phone,
    Schema,
    SchemaEncoder,
)


class JWTDummy(JWTToken):
    @classmethod
    def token_config(cls):
        return dict(
            key="secret",
            algorithms=["HS256"],
        )


DATE_CASES = (
    (
        Date,
        "1990-01-01",
        "1990-01-01",
        date(1990, 1, 1),
        date,
    ),
    (
        Date,
        date(1990, 1, 1),
        "1990-01-01",
        date(1990, 1, 1),
        date,
    ),
    (
        Date,
        "19900101",
        "1990-01-01",
        date(1990, 1, 1),
        date,
    ),
    (
        DateTime,
        "1990-01-01T00:00:00+00:00",
        "1990-01-01T00:00:00+00:00",
        datetime(1990, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        datetime,
    ),
    (
        DateTime,
        "1990-01-01T00:00:00-02:00",
        "1990-01-01T02:00:00+00:00",
        datetime(1990, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
        datetime,
    ),
    (
        DateTime,
        datetime(
            1990, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(seconds=-7200))
        ),
        "1990-01-01T02:00:00+00:00",
        datetime(1990, 1, 1, 2, 0, 0, tzinfo=timezone.utc),
        datetime,
    ),
)

FAIL_CASES = (
    (Phone, "000000000000"),
    (Phone, "+526ZA99321234"),
    (Phone, "+52 664 123 1234"),
    (Phone, "+52 (664) 123-1234"),
    (DateTime, "19900101"),
)

TYPES_GOOD = (
    (Email, "example@example.com"),
    (IANATimeZone, "America/Tijuana"),
    (
        JWTDummy,
        "eyJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE1MTYyMzkwMjJ9.zeQQi9iFCH7yF4Sg5LCfm8OsSehjq9NvgIpK4k3ypRA",
    ),
)
TYPES_BAD = (
    (Email, "ex@ample@example.com"),
    (Email, "ex@amp$le@example.com"),
    (Email, "example@exampl.e.com.e"),
    (Email, "@example.com"),
    (Email, ""),
    (IANATimeZone, "Some/Place"),
    (
        JWTDummy,
        "",
    ),
    (
        JWTDummy,
        "eyJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE1MTYyMzkwMjJ9.juag2QwZf6dx_4REp0MzVPXEx4KkEtEIl1TxAzP30E8",
    ),
)


def test_define_class_from_schema_no_fields():
    class SchemaTest(Schema):
        pass


def test_define_class_from_schema_single_str_field():
    class SchemaTest(Schema):
        field: str

    obj = SchemaTest(field="field")

    assert obj.field == "field"


def test_define_class_from_schema_single_optional_str_field():
    class SchemaTest(Schema):
        field: str
        optional: str | None = None

    obj = SchemaTest(field="field")

    assert obj.field == "field"
    assert obj.optional is None


def test_parse_from_dict_and_encoder():
    data = {
        "field_one": "One",
        "field_two": 2,
        "field_tre": "eb02a39e-4fa4-422c-954b-5446fd71a5e5",
        "field_fou": "1990-01-01",
    }

    class DummySchema(Schema):
        field_one: str
        field_two: int
        field_tre: UUID
        field_fou: Date
        field_fiv: str | None

    obj = DummySchema.from_dict(data)

    assert isinstance(obj.field_one, str)
    assert isinstance(obj.field_two, int)
    assert isinstance(obj.field_tre, UUID)
    assert isinstance(obj.field_fou, Date)
    assert obj.field_fiv is None

    json = dumps(obj, cls=SchemaEncoder)

    parsed_json = loads(json)

    parsed = DummySchema.from_dict(data)
    assert parsed == obj

    assert obj.to_dict() == {**obj.to_minimal_dict(), "field_fiv": None}


def test_parse_from_dict_with_list():
    data = {
        "field": ["1", "2"],
    }

    class DummySchema(Schema):
        field: List[str]

    obj = DummySchema.from_dict(data)

    assert isinstance(obj.field, list)
    assert all((isinstance(value, str) for value in obj.field))


def test_parse_from_dict_with_list_of_schemas():
    data = {
        "field": [
            {"field": "value"},
            {"field": "value"},
        ],
    }

    class DummySchemaOne(Schema):
        field: str

    class DummySchemaTwo(Schema):
        field: List[DummySchemaOne]

    obj = DummySchemaTwo.from_dict(data)

    assert isinstance(obj.field, list)
    assert all((isinstance(value, DummySchemaOne) for value in obj.field))


def test_parse_from_dict_with_list_of_schemas_with_optional_field():
    data = {
        "field": [
            {"field": "value"},
            {"field": "value", "extra": "foo"},
        ],
    }

    class DummySchemaOne(Schema):
        field: str
        extra: str | None

    class DummySchemaTwo(Schema):
        field: List[DummySchemaOne]

    obj = DummySchemaTwo.from_dict(data)

    assert isinstance(obj.field, list)
    assert all((isinstance(value, DummySchemaOne) for value in obj.field))


def test_parse_from_dict_with_list_of_schemas_non_homogeneous():
    data = {
        "field": [
            {"field": "value"},
            {"field": "value", "extra": "foo"},
        ],
    }

    class DummySchemaOne(Schema):
        field: str

    class DummySchemaTwo(Schema):
        field: List[DummySchemaOne]

    with pytest.raises(ValueError) as e_info:
        obj = DummySchemaTwo.from_dict(data)


def test_from_dict_with_extra_arguments_fail():
    data = {"field": "value", "extra": "foo"}

    class DummySchemaOne(Schema):
        field: str

    with pytest.raises(ValueError) as e_info:
        obj = DummySchemaOne.from_dict(data)


def test_from_dict_with_schema_on_data():
    class DummySchemaOne(Schema):
        field: str

    class DummySchemaTwo(Schema):
        field: List[DummySchemaOne]

    data = {
        "field": [
            {"field": "value"},
            DummySchemaOne.from_dict({"field": "value"}),
        ],
    }

    obj = DummySchemaTwo.from_dict(data)

    assert isinstance(obj.field, list)
    assert all((isinstance(value, DummySchemaOne) for value in obj.field))


def test_bad_type_hint_type():
    with pytest.raises(AttributeError) as e_info:

        class DummySchemaOne(Schema):
            field: Tuple[str]


def test_bad_type_hint_union():
    with pytest.raises(AttributeError) as e_info:

        class DummySchemaOne(Schema):
            field: str | int


def test_bad_type_hint_union_method():
    with pytest.raises(AttributeError) as e_info:
        field = str | int
        MetaSchema._get_type_from_union(field, "foo")


def test_extra_kwargs_on_schema():
    class SchemaTest(Schema):
        field: str

    with pytest.raises(ValueError) as e_info:
        SchemaTest(field="s", extra="foo")


def test_schema_repr_void():
    obj = Schema()

    assert repr(obj) == "<Schema >"


def test_schema_repr_one_field():
    class SchemaTest(Schema):
        field: str

    obj = SchemaTest(field="1")

    assert repr(obj) == "<SchemaTest field='1' >"


def test_enforce_schema_on_dict():
    class SchemaTest(Schema):
        field: str

    data = {"field": "1"}
    parsed = Schema.enforce(SchemaTest, data)
    assert isinstance(parsed, SchemaTest)


def test_enforce_schema_on_schema():
    class SchemaTest(Schema):
        field: str

    data = SchemaTest.from_dict({"field": "1"})
    parsed = Schema.enforce(SchemaTest, data)
    assert isinstance(parsed, SchemaTest)


def test_enforce_schema_on_none_allow_none():
    class SchemaTest(Schema):
        field: str

    parsed = Schema.enforce(SchemaTest, None, allow_none=True)
    assert parsed is None


def test_enforce_schema_on_none():
    class SchemaTest(Schema):
        field: str

    with pytest.raises(ValueError) as e:
        Schema.enforce(SchemaTest, None)


def test_enforce_schema_with_non_schema():
    class SchemaTest(TypedDict):
        field: str

    data = SchemaTest(field="a")

    with pytest.raises(TypeError) as e:
        Schema.enforce(SchemaTest, data)


def test_enforce_schema_with_non_as_schema():
    with pytest.raises(TypeError) as e:
        Schema.enforce(None, None)


def test_enforce_schema_with_non_as_schema_allow_none():
    parsed = Schema.enforce(None, None, allow_none=True)
    assert parsed is None


def test_enforce_schema_on_dict_fail_parse():
    class SchemaTest(Schema):
        field: str

    data = {"field": "1", "foo": "bar"}

    with pytest.raises(ValueError) as e_info:
        Schema.enforce(SchemaTest, data)


def test_enforce_schema_on_dict_fail_bad_type():
    data = {"field": "1", "foo": "bar"}

    with pytest.raises(TypeError) as e_info:
        Schema.enforce(str, data)


def test_json_encoder():
    class SchemaTest(Schema):
        field: str

    data = {
        "a": SchemaTest(field="1"),
        "b": UUID("eb02a39e-4fa4-422c-954b-5446fd71a5e5"),
        "c": date(1990, 1, 1),
        "d": datetime(1990, 1, 1, 1, 1),
        "e": "str",
        "f": Phone("+526641231234"),
    }

    json = dumps(data, cls=SchemaEncoder)
    parsed_json = loads(json)
    re_dump_json = dumps(parsed_json)

    assert json == re_dump_json, re_dump_json


def test_schema_inequality_same_schema_different_values():
    class SchemaTest(Schema):
        field: str

    assert SchemaTest(field="1") != SchemaTest(field="2")


def test_schema_inequality_different_schema():
    class SchemaOne(Schema):
        field: str

    class SchemaTwo(Schema):
        field: str

    assert SchemaOne(field="1") != SchemaTwo(field="2")


@pytest.mark.parametrize(
    ("_type", "in_string", "out_string", "out_object", "out_obj_class"),
    (*DATE_CASES,),
)
def test_internal_object_type_str(
    _type, in_string, out_string, out_object, out_obj_class
):
    value = _type(in_string)

    assert _type.object_class == out_obj_class
    assert isinstance(out_object, _type.object_class)
    assert value.value == out_object
    assert str(value) == out_string


@pytest.mark.parametrize(
    ("_type", "in_string"),
    FAIL_CASES,
)
def test_internal_object_type_str_error(_type, in_string):
    with pytest.raises(ValueError) as e_info:
        value = _type(in_string)


@pytest.mark.parametrize(
    ("_type", "string"),
    TYPES_GOOD,
)
def test_types(_type, string):
    value = _type(string)
    assert isinstance(value, _type)
    assert str(value) == string


@pytest.mark.parametrize(
    ("_type", "string"),
    TYPES_BAD,
)
def test_type_error(_type, string):
    with pytest.raises(ValueError):
        value = _type(string)


def test_jwt_internal_object():
    token = (
        "eyJhbGciOiJIUzI1NiJ9."
        "eyJpYXQiOjE1MTYyMzkwMjJ9."
        "zeQQi9iFCH7yF4Sg5LCfm8OsSehjq9NvgIpK4k3ypRA"
    )
    parsed_token = JWTDummy(token)
    assert parsed_token.claims["iat"] == 1516239022


def test_abstract_convert_method():
    assert InternalObjectTypeString.convert("") is NotImplemented


def test_jwt_configuration_dict():
    assert isinstance(JWTToken.token_config(), dict)


def test_jwt_parse_from_header():
    header = (
        "Bearer "
        "eyJhbGciOiJIUzI1NiJ9."
        "eyJpYXQiOjE1MTYyMzkwMjJ9."
        "zeQQi9iFCH7yF4Sg5LCfm8OsSehjq9NvgIpK4k3ypRA"
    )
    token = JWTDummy.from_http_header(header)
    assert isinstance(token, JWTDummy)


def test_jwt_parse_from_header_no_header():
    with pytest.raises(ValueError) as e:
        JWTDummy.from_http_header(None)


def test_jwt_parse_from_header_bad_header():
    header = "Bearer"
    with pytest.raises(ValueError) as e:
        JWTDummy.from_http_header(header)
