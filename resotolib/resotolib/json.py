import json
from datetime import timedelta

import jsons
import cattrs
from cattrs import override
from cattrs.gen import make_dict_unstructure_fn
import attrs
from typing import TypeVar, Any, Type, Optional, Dict

from jsons import set_deserializer, set_serializer

from resotolib.durations import parse_duration, duration_str
from resotolib.types import Json, JsonElement

AnyT = TypeVar("AnyT")


converter = cattrs.Converter()
converter.register_unstructure_hook_factory(
    attrs.has,
    lambda cls: make_dict_unstructure_fn(
        cls, converter, **{a.name: override(omit=True) for a in attrs.fields(cls) if a.name.startswith("_")}
    ),
)


def to_json(node: Any, **kwargs: Any) -> Json:
    """
    Use this method, if the given node is known as complex object,
    so the result will be a json object.
    """
    unstructured = converter.unstructure(node)
    if strip_attr := kwargs.get("strip_attr"):
        if isinstance(strip_attr, str):
            if unstructured.get(strip_attr):
                del unstructured[strip_attr]
        else:
            for field in strip_attr:
                if unstructured.get(field):
                    del unstructured[field]
    result = jsons.dump(  # type: ignore
        unstructured,
        strip_microseconds=True,
        strip_nulls=True,
        # class variables have to stripped manually via strip_attr=
        # see: https://github.com/ramonhagenaars/jsons/issues/177
        # strip_class_variables=True,
        **kwargs,
    )
    return result


def to_json_str(node: Any, json_kwargs: Optional[Dict[str, object]] = None, **kwargs: Any) -> str:
    """
    Json string representation of the given object.
    """
    return json.dumps(to_json(node, **kwargs), **(json_kwargs or {}))


def from_json(json: JsonElement, clazz: Type[AnyT], **kwargs: Any) -> AnyT:
    """
    Loads a json object into a python object.
    :param json: the json object to load.
    :param clazz: the type of the python object.
    :return: the loaded python object.
    """
    return jsons.load(json, clazz, **kwargs) if clazz != dict else json  # type: ignore


def timedelta_to_json(td: timedelta, **_: Any) -> str:
    return duration_str(td)


def timedelta_from_json(js: str, _: type = object, **__: Any) -> timedelta:
    return parse_duration(js)


set_deserializer(timedelta_from_json, timedelta)
set_serializer(timedelta_to_json, timedelta)
