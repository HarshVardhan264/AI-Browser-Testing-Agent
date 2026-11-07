import os
import re

from dotenv import load_dotenv

# .env is the source of truth: it wins over stale variables in the shell.
load_dotenv(override=True)

ENV_VARS = {
    "email": "TEST_EMAIL",
    "phone": "TEST_PHONE",
    "username": "TEST_USERNAME",
    "password": "TEST_PASSWORD",
    "first_name": "TEST_FIRST_NAME",
    "last_name": "TEST_LAST_NAME",
    "full_name": "TEST_FULL_NAME",
    "company": "TEST_COMPANY",
    "country": "TEST_COUNTRY",
    "city": "TEST_CITY",
    "state": "TEST_STATE",
    "zip": "TEST_ZIP",
    "address": "TEST_ADDRESS",
    "gender": "TEST_GENDER",
    "date_of_birth": "TEST_DATE_OF_BIRTH",
}

# Words in a test case that make each key relevant. Used only when the
# test case text is supplied to get_test_data().
RELEVANCE = {
    "email": ["email", "e-mail", "login", "log in", "sign in", "register", "sign up"],
    "phone": ["phone", "mobile", "telephone", "whatsapp", "contact number"],
    "username": ["username", "user name", "user id", "login", "log in", "sign in"],
    "password": ["password", "login", "log in", "sign in", "register", "sign up"],
    "first_name": ["first name", "given name"],
    "last_name": ["last name", "surname", "family name"],
    "full_name": ["full name", "your name"],
    "company": ["company", "business", "organization", "organisation"],
    "country": ["country"],
    "city": ["city", "town"],
    "state": ["state", "province", "region"],
    "zip": ["zip", "postal", "postcode"],
    "address": ["address"],
    "gender": ["gender", "sex"],
    "date_of_birth": ["date of birth", "dob", "birthday", "birth date"],
}


def _mentioned(key, text):
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text)
        for term in RELEVANCE.get(key, [])
    )


def get_test_data(test_case=None):
    """Return configured values as trimmed, non-empty strings.

    With no argument, every configured value is returned (previous behaviour).
    With the test case text, only values relevant to it are returned.
    """
    text = str(test_case).lower() if test_case else None
    data = {}
    for key, env_name in ENV_VARS.items():
        value = os.getenv(env_name, "").strip()
        if not value:
            continue
        if text is not None and not _mentioned(key, text):
            continue
        data[key] = value
    return data