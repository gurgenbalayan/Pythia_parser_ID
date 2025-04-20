import json
import re

import aiohttp
from bs4 import BeautifulSoup
from utils.logger import setup_logger
import os
from dotenv import load_dotenv
load_dotenv()

STATE = os.getenv("STATE")
logger = setup_logger("scraper")



async def fetch_company_details(url: str) -> dict:
    try:
        match = re.search(r"business/(\d+)/", url)
        if match:
            id = match.group(1)
            url_search = "https://sosbiz.idaho.gov/api/Records/businesssearch"
            payload = json.dumps({
                "SEARCH_VALUE": id,
                "STARTS_WITH_YN": True,
                "CRA_SEARCH_YN": False,
                "ACTIVE_ONLY_YN": False,
                "FILING_DATE": {
                    "start": None,
                    "end": None
                }
            })
            headers = {
                'Content-Type': 'application/json'
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(url_search, data=payload) as response:
                    response.raise_for_status()
                    data = json.loads(await response.text())
                    result = await parse_html_name_agent(data)
                    record_num, id, name, agent = result["record_num"], result["id"], result["name"], result["agent"]
        else:
            logger.error(f"Error fetching data for query '{url}'")
            return []
        new_url = re.sub(r'(?<=business/)\d+(?=/)', id, url)
        async with aiohttp.ClientSession() as session:
            async with session.get(new_url) as response:
                response.raise_for_status()
                data = json.loads(await response.text())
                return await parse_html_details(data, record_num, id, name, agent)
    except Exception as e:
        logger.error(f"Error fetching data for query '{url}': {e}")
        return []
async def fetch_company_data(query: str) -> list[dict]:
    url = "https://sosbiz.idaho.gov/api/Records/businesssearch"
    payload = json.dumps({
        "SEARCH_VALUE": query,
        "STARTS_WITH_YN": True,
        "CRA_SEARCH_YN": False,
        "ACTIVE_ONLY_YN": False,
        "FILING_DATE": {
            "start": None,
            "end": None
        }
    })
    headers = {
        'Content-Type': 'application/json'
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(url, data=payload) as response:
                response.raise_for_status()
                data = json.loads(await response.text())
                return await parse_html_search(data)
    except Exception as e:
        logger.error(f"Error fetching data for query '{query}': {e}")
        return []

async def parse_html_search(data: dict) -> list[dict]:
    results = []
    for entity_id, data_row in data["rows"].items():
        entity_name = data_row.get("TITLE", [""])[0]  # берём первую строку из TITLE
        status = data_row.get("STATUS", "")
        id = data_row.get("RECORD_NUM", "").lstrip("0")
        results.append({
                "state": STATE,
                "name": entity_name,
                "status": status,
                "id": entity_id,
                "url": f"https://sosbiz.idaho.gov/api/FilingDetail/business/{id}/false"
            })
    return results

async def parse_html_name_agent(data: dict) -> dict:
    for entity_id, data_row in data["rows"].items():
        entity_name = data_row.get("TITLE", [""])[0]  # берём первую строку из TITLE
        agent = data_row.get("AGENT", "")
        record_num = data_row.get("RECORD_NUM", "")
        return {
            "record_num": record_num,
            "id": entity_id,
            "name": entity_name,
            "agent": agent
        }


async def parse_html_details(data: dict, record_num: str, id: str, name: str, agent: str) -> dict:
    async def fetch_documents(record_num: str) -> list[dict]:
        url = f"https://sosbiz.idaho.gov/api/History/business/{record_num}"
        headers = {
            'Content-Type': 'application/json'
        }
        results = []
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    data = json.loads(await response.text())
                    base_url = "https://sosbiz.idaho.gov"
                    for amendment in data["AMENDMENT_LIST"]:
                        try:
                            download_link = base_url + amendment["DOWNLOAD_LINK"]
                            file_name = amendment["AMENDMENT_TYPE"]
                            file_date = amendment["AMENDMENT_DATE"]
                            results.append({
                                "name": file_name,
                                "date": file_date,
                                "link": download_link,
                            })
                        except Exception as e:
                            continue
                    return results
        except Exception as e:
            logger.error(f"Error fetching data for record_num '{record_num}': {e}")
            return []


    detail_map = {item["LABEL"]: item["VALUE"] for item in data.get("DRAWER_DETAIL_LIST", [])}
    mailing_address = detail_map.get("Mailing Address") or ""
    principal_address = detail_map.get("Principal Address") or ""
    document_images = await fetch_documents(record_num)
    status = detail_map.get("Status")
    date_registered = detail_map.get("Initial Filing Date")
    entity_type = detail_map.get("Filing Type")
    return {
        "state": STATE,
        "name": name,
        "status": status.strip(),
        "registration_number": id,
        "date_registered": date_registered.strip(),
        "entity_type": entity_type.strip(),
        "agent_name": agent,
        "principal_address": principal_address.strip(),
        "mailing_address": mailing_address.strip(),
        "document_images": document_images
    }