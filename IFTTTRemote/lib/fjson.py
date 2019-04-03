import json


# Loads a JSON and decodes the unicode strings
def json_load(text):
    return __decode_unicode(json.loads(text, object_hook=__decode_unicode), ignore_dicts=True)


def __decode_unicode(data, ignore_dicts=False):
    # If this is a unicode string, return its string representation
    if isinstance(data, unicode):
        return data.encode('utf-8')
    # If this is a list of values, return list of decoded values
    if isinstance(data, list):
        return [__decode_unicode(item, ignore_dicts=True) for item in data]
    # If this is a dictionary, return dictionary of decoded keys and values,
    # but only if we haven't already decoded it
    if isinstance(data, dict) and not ignore_dicts:
        return {
            __decode_unicode(key, ignore_dicts=True): __decode_unicode(value, ignore_dicts=True)
            for key, value in data.iteritems()
        }
    # If it's anything else, return it in its original form
    return data
