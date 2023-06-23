import typing as t

from datetime import (
    date,
    datetime,
    timezone,
)
from enum import Enum
from functools import reduce
from json import JSONEncoder
from re import fullmatch
from types import UnionType, NoneType
from uuid import UUID
from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

import jwt
import jwt.algorithms
import phonenumbers


JsonType = t.Union[
    None, int, float, str, bool, list["JsonType"], dict[str, "JsonType"]
]
JsonRoot = dict[str, JsonType]


class InternalObjectTypeString(str):
    object_class: t.Type[t.Any]
    value: t.Any

    def __new__(cls, value: str | t.Any) -> "InternalObjectTypeString":
        try:
            string, obj = cls.convert(value)
        except Exception as e:
            raise ValueError
        instance = str.__new__(cls, string)
        instance.value = obj
        return instance

    @classmethod
    def convert(cls, value: str | t.Any) -> t.Tuple[str, t.Any]:
        return NotImplemented


class Date(InternalObjectTypeString):
    object_class = date

    @classmethod
    def convert(cls, value: str | date) -> t.Tuple[str, date]:
        if isinstance(value, str):
            obj = cls.object_class.fromisoformat(value)
            string = obj.isoformat()
        if isinstance(value, cls.object_class):
            obj = value
            string = obj.isoformat()
        return string, obj


class DateTime(InternalObjectTypeString):
    object_class = datetime

    @classmethod
    def convert(cls, value: str | datetime) -> t.Tuple[str, datetime]:
        if isinstance(value, str) and len(value) > 10:
            obj = cls.object_class.fromisoformat(value).astimezone(timezone.utc)
            string = obj.isoformat()
        if isinstance(value, cls.object_class):
            obj = value.astimezone(timezone.utc)
            string = obj.isoformat()
        return string, obj


class JWTDecodeKwargs(t.TypedDict, total=False):
    key: t.Union["jwt.algorithms.AllowedPublicKeys", str, bytes]  # type: ignore
    algorithms: list[str]
    options: dict[str, t.Any] | None
    detached_payload: bytes | None


class JWTEncodeKwargs(t.TypedDict, total=False):
    key: t.Union["jwt.algorithms.AllowedPrivateKeys", str, bytes]  # type: ignore
    algorithm: str
    headers: JsonRoot | None
    json_encoder: type[JSONEncoder] | None


class JWTToken(str):
    claims: JsonRoot

    def __new__(cls, token: str | bytes) -> "JWTToken":
        try:
            claims = jwt.decode(token, **cls.token_config())
        except Exception:
            raise ValueError("Invalid string for JWT Token")
        obj = str.__new__(cls, token)
        obj.claims = claims
        return obj

    @classmethod
    def token_config(cls) -> JWTDecodeKwargs:
        from os import environ

        JWT_SECRET = "JWT_SECRET"
        return dict(
            key=environ.get(JWT_SECRET, ""),
            algorithms=["HS256"],
        )

    @classmethod
    def from_decode_kwargs(
        cls, decode_kwargs: JWTDecodeKwargs
    ) -> "JWTEncodeKwargs":
        return JWTEncodeKwargs(
            algorithm=decode_kwargs["algorithms"][0],
            json_encoder=SchemaEncoder,
            headers=None,
        )

    @classmethod
    def generate(
        cls, data: JsonRoot, algorithm: str | None = None
    ) -> "JWTToken":
        encode_config = cls.from_decode_kwargs(cls.token_config())
        if algorithm is not None:
            encode_config["algorithm"] = algorithm
        return cls(jwt.encode(data, **encode_config))

    @classmethod
    def from_http_header(cls, header: str | None) -> "JWTToken":
        if header is None:
            raise ValueError("Missing header value.")
        try:
            _, token = header.split()
        except Exception:
            raise ValueError("Unable to distinguish bearer and token.")
        return cls(token)


class Phone(InternalObjectTypeString):
    object_class = phonenumbers.PhoneNumber

    @classmethod
    def convert(
        cls, value: str | phonenumbers.PhoneNumber
    ) -> t.Tuple[str, phonenumbers.PhoneNumber]:
        is_string = isinstance(value, str)
        is_phone_obj = isinstance(value, phonenumbers.PhoneNumber)
        try:
            if not is_string and not is_phone_obj:
                raise TypeError
            if is_phone_obj:
                obj: phonenumbers.PhoneNumber = value  # type: ignore
            else:
                obj = phonenumbers.parse(
                    value, None, keep_raw_input=True  # type: ignore
                )
        except (TypeError, phonenumbers.NumberParseException) as e:
            raise ValueError

        string = phonenumbers.format_number(
            obj,
            phonenumbers.PhoneNumberFormat.E164,
        )
        if obj.raw_input and obj.raw_input != string:
            raise ValueError("Incorrect format for phone number.")
        return string, obj


class RegexValidatedString(str):
    regex = ".*"

    def __new__(cls, string: str) -> "RegexValidatedString":
        if not fullmatch(cls.regex, string):
            raise ValueError
        return str.__new__(cls, string)


class Email(RegexValidatedString):
    regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"


class IANATimeZone(str):
    def __new__(cls, timezone: str) -> "IANATimeZone":
        try:
            ZoneInfo(timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError
        return str.__new__(cls, timezone)


class MetaSchema(type):
    _field_array: tuple[str, ...]
    _field_optional: tuple[str, ...]
    _field_types: dict[str, type]

    def __new__(
        cls, name: str, bases: tuple[str, ...], attrs: dict[str, t.Any] = {}
    ) -> "MetaSchema":
        annotations = attrs.get("__annotations__", {})
        field_optional: list[str] = []
        field_array: list[str] = []
        field_types: dict[str, type] = {}
        for attr_name, _type in annotations.items():
            # To detect if it's an Optional field, a Union with None.
            if cls._none_type_compatible(_type):
                field_optional.append(attr_name)
                _type = cls._get_type_from_union(_type, attr_name)

            # To detect if it's a List type hint.
            if cls._array_type_compatible(_type):
                field_array.append(attr_name)
                _type = cls._get_type_from_list(_type, attr_name)

            # by this point we should have a concrete type
            if not isinstance(_type, type):
                raise AttributeError(
                    f"Bad attribute type hint for '{attr_name}'",
                )

            field_types[attr_name] = _type

        obj = super().__new__(cls, name, bases, attrs)  # type: ignore
        obj._field_array = tuple(field_array)
        obj._field_optional = tuple(field_optional)
        obj._field_types = field_types
        return obj

    @classmethod
    def _none_type_compatible(cls, field: type) -> bool:
        """
        This method will enforce a validation to determine if it's a Union with None
        exclusively, the meaning of this would end up determining if it's an
        optional field or not.
        """
        return (
            isinstance(field, UnionType)
            and len(field.__args__) == 2
            and NoneType in field.__args__
        )

    @classmethod
    def _array_type_compatible(cls, field: type) -> bool:
        """
        This method will enforce a validation to determine if it's a `typing.List` object
        with.

        For now we will only support homogeneous arrays of a concrete type.
        """
        return hasattr(field, "__origin__") and field.__origin__ == list

    @classmethod
    def _get_type_from_list(cls, field: UnionType, field_name: str) -> type:
        return field.__args__[0]  # type: ignore

    @classmethod
    def _get_type_from_union(cls, field: UnionType, field_name: str) -> type:
        if len(field.__args__) != 2 or NoneType not in field.__args__:
            raise AttributeError(
                f"Attributes must be a concrete type or optional concrete type '{field_name}'"
            )
        return [_t for _t in field.__args__ if _t != NoneType][0]  # type: ignore


class Schema(metaclass=MetaSchema):
    def __init__(self, **kwargs: dict[str, t.Any]) -> None:
        annotations = self._annotations()
        extra_keys = set(kwargs.keys()).difference(annotations.keys())
        if extra_keys:
            raise ValueError(f"Extra arguments provided {extra_keys}.")
        for attribute, _type in self.__class__._field_types.items():
            value = kwargs.get(attribute, None)
            _type_constructor = (
                (lambda x: _type.from_dict(x))
                if issubclass(_type, Schema)
                else _type
            )
            if not callable(_type_constructor):
                # TODO: get this line covered in a test.
                raise ValueError(
                    "Type hint does not allow for object creation by call."
                )
            if isinstance(value, _type) or (
                value is None and attribute in self.__class__._field_optional
            ):
                self.__dict__[attribute] = value
            elif isinstance(value, list) and attribute in self._field_array:
                self.__dict__[attribute] = [_type_constructor(v) for v in value]
            else:
                self.__dict__[attribute] = _type_constructor(value)

    def __repr__(self) -> str:
        returnable = f"<{self.__class__.__name__} "
        for k, v in self.to_dict().items():
            returnable += f"{k}={v.__repr__()} "
        return returnable + ">"

    def to_dict(self) -> JsonRoot:
        return {k: getattr(self, k) for k in self.__class__._annotations()}

    def to_minimal_dict(self) -> JsonRoot:
        return {k: v for k, v in self.to_dict().items() if v is not None}

    @classmethod
    def from_dict(cls, data: t.Union[JsonRoot, "Schema"]) -> "Schema":
        if isinstance(data, Schema):
            return data

        annotations = cls._annotations().keys()
        if set(data.keys()) - annotations:
            raise ValueError("Arguments outside schema were provided.")
        kwargs: dict[str, t.Any] = {
            **cls._nullable_fields(),
            **cls._default_values(),
            **{k: v for k, v in data.items() if k in annotations},
        }

        return cls(**kwargs)

    @classmethod
    def _annotations(cls) -> dict[str, type]:
        return reduce(
            lambda acc, cur: {**acc, **getattr(cur, "__annotations__", {})},
            filter(lambda x: x is not Schema, reversed(cls.__mro__)),
            {},
        )

    @classmethod
    def _default_values(cls) -> dict[str, t.Any]:
        return {
            k: getattr(cls, k)
            for k in set(dir(cls)).intersection(cls._annotations())
        }

    @classmethod
    def _nullable_fields(cls) -> dict[str, None]:
        return {
            field: None
            for field in cls._annotations().keys()
            if field in cls._field_optional
        }

    @classmethod
    def enforce(
        cls,
        schema: t.Optional[t.Type["Schema"]],
        data: t.Union[JsonRoot, "Schema", None],
        allow_none: bool = False,
    ) -> t.Union["Schema", JsonRoot, None]:
        """
        This serves as a generic to convert a dictionary output as a schema,
        meant to be used driven by a function's type annotations.
        """
        if schema is None and allow_none is True:
            return data
        if schema is None and allow_none is False:
            raise TypeError("Schema argument can not be None")

        # At this point we know schema is not None.
        if not issubclass(schema, Schema):  # type: ignore
            raise TypeError("Schema argument is not derived from class Schema.")

        if data is None and allow_none is True:
            return data
        if data is None and allow_none is False:
            raise ValueError("No data provided to convert in to schema.")

        # At this point we know that schema is a subclass of Schema.
        if isinstance(data, schema):  # type: ignore
            return data

        try:
            # And that data is the correct "json compatible" object
            # we want to convert in to schema.
            parsed = schema.from_dict(data)  # type: ignore
        except Exception:
            raise ValueError("Error during parsing")

        return parsed

    def __eq__(self, other: t.Any) -> bool:
        if (
            isinstance(other, self.__class__)
            and self.__class__ == other.__class__
        ):
            for attr in self._annotations():
                if getattr(self, attr) != getattr(other, attr):
                    return False
            return True
        return False


class SchemaEncoder(JSONEncoder):
    def default(self, obj):  # type: ignore
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, Schema):
            return obj.to_dict()
        return super().default(obj)
