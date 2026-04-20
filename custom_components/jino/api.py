from __future__ import annotations

import datetime
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class BillingApiError(Exception):
    """Base API error."""


@dataclass(slots=True)
class JinoCredentials:
    login: str
    password: str


@dataclass(slots=True)
class NightscoutAccount:
    login: str
    password: str


def day(n: int) -> str:
    n = abs(int(n))
    if 11 <= (n % 100) <= 14:
        return "дней"
    last = n % 10
    if last == 1:
        return "день"
    if 2 <= last <= 4:
        return "дня"
    return "дней"


def time_to_pay(name: str, due_date: str, service_name: str = "Jino") -> tuple[str, int]:
    due = datetime.datetime.strptime(due_date, "%d.%m.%Y")
    now_ts = int(time.time())
    due_ts = int(due.timestamp()) + 10800
    days_left = (due_ts - now_ts) // 86400
    dword = day(days_left)

    if days_left == 0:
        msg = f"Сегодня срок оплаты {service_name} - {name}!"
    elif 0 < days_left <= 5:
        msg = f"Через {days_left} {dword} нужно оплатить {service_name} - {name}!"
    elif days_left < 0:
        msg = f"Просрочена оплата {service_name} - {name}!!!"
    else:
        msg = f"Все в порядке! Оплачивать {service_name} - {name} нужно через {days_left} {dword}."

    return msg, days_left


def normalize_date(date_str: str | None) -> str | None:
    if not date_str:
        return None

    date_str = date_str.strip()

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_str):
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d.%m.%Y")

    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", date_str):
        return date_str

    return None


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = value.replace("ё", "e")
    value = re.sub(r"[^a-z0-9а-я_-]+", "_", value, flags=re.IGNORECASE)
    value = re.sub(r"_+", "_", value)
    return value.strip("_")


def parse_nightscout_accounts(raw: str | list[dict[str, Any]] | None) -> list[NightscoutAccount]:
    if not raw:
        return []

    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as err:
            raise BillingApiError("Invalid Nightscout accounts JSON") from err

    if not isinstance(data, list):
        raise BillingApiError("Nightscout accounts must be a list")

    accounts: list[NightscoutAccount] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise BillingApiError(f"Nightscout account #{idx + 1} must be an object")

        login = str(item.get("login") or "").strip()
        password = str(item.get("password") or "")

        if not login or not password:
            raise BillingApiError("Nightscout account must include login and password")

        accounts.append(NightscoutAccount(login=login, password=password))

    return accounts


class JinoDomainsClient:
    LOGIN_PAGE = "https://auth.jino.ru/login/"
    GRAPHQL_URL = "https://graphql.jino.ru/user/"
    REFERER = "https://cp.jino.ru/domains/"

    LIST_DOMAINS_QUERY = """
    query ListDomains($first: Int, $after: String, $sort: [UserDomainSortEnum!]) {
      me {
        domain(first: $first, after: $after, sort: $sort) {
          edges {
            node {
              id
              domain
              rawDomain
            }
            cursor
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
    }
    """

    DOMAIN_INFO_QUERY = """
    query DomainAdditionalInfo ($id: ID!) {
      node(id: $id) {
        ... on UserDomain {
          id
          domain
          renewal {
            autorenewalEnabled
            expireDate
            isExpired
            expiring
            renewalCost
            renewalAvailable
            canBeRenewedFromBalance
          }
          whoisData {
            expireDate
          }
        }
      }
    }
    """

    BALANCE_QUERY = """
    query GetBalance {
      me {
        funds
        realFunds
        bonusFunds
        billingData {
          paymentsCount
          expirationDays
          expirationDate
          expirationLabel
          minPayment
          minPersonPayment
          minOrgPayment
          maxPayment
          autoinvoiceEnabled
        }
      }
    }
    """

    def __init__(self, credentials: JinoCredentials, timeout: int = 30) -> None:
        self._credentials = credentials
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/147.0.0.0 Safari/537.36"
                )
            }
        )

    @staticmethod
    def _extract_csrf(html: str) -> str | None:
        patterns = [
            r"myv\.csrftoken\s*=\s*'([^']+)'",
            r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _is_retryable_error(err: Exception) -> bool:
        if isinstance(err, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return True

        if isinstance(err, requests.exceptions.HTTPError):
            response = err.response
            if response is None:
                return False
            return response.status_code in (500, 502, 503, 504)

        return False

    def authenticate(self) -> None:
        response = self._session.get(self.LOGIN_PAGE, timeout=self._timeout)
        response.raise_for_status()

        csrf = self._extract_csrf(response.text)
        if not csrf:
            raise BillingApiError("Jino CSRF token not found")

        response = self._session.post(
            self.LOGIN_PAGE,
            data={
                "login": self._credentials.login,
                "password": self._credentials.password,
                "csrfmiddlewaretoken": csrf,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": "https://auth.jino.ru",
                "Referer": self.LOGIN_PAGE,
            },
            allow_redirects=True,
            timeout=self._timeout,
        )
        response.raise_for_status()

    def _build_headers(self) -> dict[str, str]:
        token = self._session.cookies.get("auth._token.keycloak")
        if not token:
            raise BillingApiError("Jino bearer token not found in cookies")

        return {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Origin": "https://cp.jino.ru",
            "Referer": self.REFERER,
        }

    def _gql(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": query,
            "variables": variables or {},
        }
        if operation_name:
            payload["operationName"] = operation_name

        last_error: Exception | None = None

        for attempt in range(3):
            try:
                response = self._session.post(
                    self.GRAPHQL_URL,
                    headers=self._build_headers(),
                    json=payload,
                    timeout=self._timeout,
                )
                response.raise_for_status()

                data = response.json()
                if data.get("errors"):
                    raise BillingApiError(json.dumps(data["errors"], ensure_ascii=False))

                return data

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as err:
                last_error = err

                if not self._is_retryable_error(err):
                    raise

                if attempt < 2:
                    time.sleep(attempt + 1)

        if last_error is not None:
            raise last_error

        raise BillingApiError("Jino GraphQL request failed without details")

    def get_balance_info(self) -> dict[str, Any]:
        result = self._gql(self.BALANCE_QUERY, operation_name="GetBalance")
        me = result["data"]["me"]
        billing = me.get("billingData") or {}

        expire_date = normalize_date(billing.get("expirationDate"))
        message = None
        days_left = None
        if expire_date:
            message, days_left = time_to_pay("balance", expire_date, "Jino")

        return {
            "funds": me.get("funds"),
            "real_funds": me.get("realFunds"),
            "bonus_funds": me.get("bonusFunds"),
            "payments_count": billing.get("paymentsCount"),
            "expiration_days": billing.get("expirationDays"),
            "expiration_date": expire_date,
            "expiration_label": billing.get("expirationLabel"),
            "min_payment": billing.get("minPayment"),
            "min_person_payment": billing.get("minPersonPayment"),
            "min_org_payment": billing.get("minOrgPayment"),
            "max_payment": billing.get("maxPayment"),
            "autoinvoice_enabled": billing.get("autoinvoiceEnabled"),
            "days_left": days_left,
            "message": message,
        }

    def get_domains(self) -> list[dict[str, Any]]:
        result = self._gql(
            self.LIST_DOMAINS_QUERY,
            variables={"first": 100, "sort": ["DOMAIN_ASC"]},
            operation_name="ListDomains",
        )

        edges = result["data"]["me"]["domain"]["edges"]
        domains: list[dict[str, Any]] = []

        for edge in edges:
            node = edge["node"]
            domain_id = node["id"]

            info = self._gql(
                self.DOMAIN_INFO_QUERY,
                variables={"id": domain_id},
                operation_name="DomainAdditionalInfo",
            )["data"]["node"]

            renewal = info.get("renewal") or {}
            whois = info.get("whoisData") or {}
            expire_date = normalize_date(renewal.get("expireDate") or whois.get("expireDate"))

            message = None
            days_left = None
            if expire_date:
                message, days_left = time_to_pay(info["domain"], expire_date, "Jino")

            domains.append(
                {
                    "domain": info["domain"],
                    "expire_date": expire_date,
                    "autorenewal_enabled": renewal.get("autorenewalEnabled"),
                    "is_expired": renewal.get("isExpired"),
                    "expiring": renewal.get("expiring"),
                    "renewal_cost": renewal.get("renewalCost"),
                    "renewal_available": renewal.get("renewalAvailable"),
                    "can_be_renewed_from_balance": renewal.get("canBeRenewedFromBalance"),
                    "days_left": days_left,
                    "message": message,
                }
            )

        return domains

    def get_all(self) -> dict[str, Any]:
        return {
            "balance": self.get_balance_info(),
            "domains": self.get_domains(),
        }


class NightscoutEasyClient:
    CP_URL = "https://cp.nightscout-easy.ru/"
    AUTH_BASE = "https://auth.nightscout-easy.ru"

    def __init__(self, account: NightscoutAccount, timeout: int = 30) -> None:
        self._account = account
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/147.0.0.0 Safari/537.36"
                )
            }
        )
        self._last_html: str | None = None

    @staticmethod
    def _extract_form_payload(form: BeautifulSoup) -> dict[str, str]:
        payload: dict[str, str] = {}

        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            payload[name] = inp.get("value", "")

        data_form_raw = form.get("data-form")
        if data_form_raw:
            data_form = json.loads(data_form_raw)
            for field in data_form.get("fields", []):
                name = field.get("name")
                if not name:
                    continue
                payload[name] = field.get("value") if field.get("value") is not None else ""

        return payload

    def _get_login_page(self) -> tuple[str, str]:
        response = self._session.get(self.CP_URL, timeout=self._timeout, allow_redirects=True)
        response.raise_for_status()
        return response.url, response.text

    def authenticate(self) -> None:
        login_url, html = self._get_login_page()

        soup = BeautifulSoup(html, "html.parser")
        form = soup.find("form")
        if not form:
            raise BillingApiError("Nightscout login form not found")

        action = form.get("action") or login_url
        if action.startswith("/"):
            action = urljoin(self.AUTH_BASE, action)
        elif action.startswith("?"):
            action = login_url.split("?", 1)[0] + action
        elif not action.startswith("http"):
            action = urljoin(self.AUTH_BASE + "/", action.lstrip("/"))

        payload = self._extract_form_payload(form)

        if "login" in payload:
            payload["login"] = self._account.login
        elif "username" in payload:
            payload["username"] = self._account.login
        elif "email" in payload:
            payload["email"] = self._account.login
        else:
            raise BillingApiError(f"Nightscout login field not found. Keys: {list(payload.keys())}")

        if "password" in payload:
            payload["password"] = self._account.password
        elif "passwd" in payload:
            payload["passwd"] = self._account.password
        else:
            raise BillingApiError(f"Nightscout password field not found. Keys: {list(payload.keys())}")

        csrftoken = self._session.cookies.get("csrftoken")
        if csrftoken and "csrfmiddlewaretoken" not in payload:
            payload["csrfmiddlewaretoken"] = csrftoken

        response = self._session.post(
            action,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": self.AUTH_BASE,
                "Referer": login_url,
            },
            timeout=self._timeout,
            allow_redirects=True,
        )
        response.raise_for_status()

        # После allow_redirects=True здесь уже финальная страница аккаунта.
        self._last_html = response.text

    def fetch_cp_html(self) -> str:
        if self._last_html:
            return self._last_html

        response = self._session.get(self.CP_URL, timeout=self._timeout, allow_redirects=True)
        response.raise_for_status()
        self._last_html = response.text
        return self._last_html

    @staticmethod
    def parse_info(html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)

        name = None
        expire_date = None

        match = re.search(r"\b(Nightscout\s+[^\n\r]+)", text)
        if match:
            name = match.group(1).strip()

        match = re.search(r"Сервис\s+доступен\s+до\s+(\d{2}\.\d{2}\.\d{4})", text, re.IGNORECASE)
        if match:
            expire_date = match.group(1)

        message = None
        days_left = None
        if name and expire_date:
            message, days_left = time_to_pay(name, expire_date, "Nightscout")

        return {
            "name": name,
            "expire_date": expire_date,
            "days_left": days_left,
            "message": message,
        }

    def get_info(self) -> dict[str, Any]:
        return self.parse_info(self.fetch_cp_html())