import time

import requests
import pandas

from loguru import logger
from retry import retry
from bs4 import BeautifulSoup
from lxml import etree


class Scrape:
    def __init__(self, link, father_id):
        self.r = requests.session()
        self.link = link
        self.father_id = father_id
        self.root = 'https://www.lily-bearing.com/'

    def run(self):
        logger.info(f'Scrape category {self.link}')

        r = self.fetch(self.link, 30)

        if r.status_code != 200:
            logger.error(f"Fetch {r.url} failed, {r.status_code}")
            return

        self.extract_category(r)

    def product_exist(self, product_id):
        """
        用id检查 product 是否存在
        :param product_id:
        :return: 1 存在, 0 不存在, -1 错误
        """
        url = f'https://products.com/product_Api.php?product_id={product_id}'
        r = self.fetch(url, 30)
        if r.status_code != 200:
            logger.critical(f"Fetch product_Api.php failed, {r.status_code}, please check your WP API")
            return -1

        json_data = r.json()
        if json_data['exist']:
            return 1
        else:
            return 0

    def extract_category(self, r):
        if r.text == "":
            return

        soup = BeautifulSoup(r.text, 'lxml')

        # extract the urls of events
        for a in soup.select('div.hang > a'):
            try:
                # Skip if this product already exist
                product_id = a.select_one('div.Product').text

                if self.product_exist(product_id):
                    # Skip if product already has
                    logger.warning(f'Product: {product_id} exist')
                    continue

                path = a['href']

                if not path:
                    continue

                logger.info(f'Find {path}')

                r = self.fetch(self.root + path, 30)

                if r.status_code != 200:
                    logger.error(f"Fetch {r.url} failed, {r.status_code}")
                    continue

                self.extract_product(path, r)

            except Exception as e:
                logger.error(f'Error: {e}')
                time.sleep(10)

    def extract_product(self, path, r):
        if r.text == "":
            return

        soup = BeautifulSoup(r.text, 'lxml')

        # product id
        product_id = soup.select_one('cite').text

        # Category
        main_category = soup.select_one('div.firstbreadcrumb > span > a:nth-child(3)').text

        # Small img
        small_img = soup.select_one('div.layui-col-md3.detail-img-box > img')['src']

        # Big img
        big_img = soup.select_one('#magnifier > div > img')['src']

        # Price
        price = soup.select_one('div.detail-img-box > div > div > span').text.replace('$ ', '')

        # Get table1, table2
        table_html = str(soup.select_one('div.layui-row > div.layui-col-md4 > div.layui-col-md9 > table'))
        table1, table2 = self.modify_table(table_html)

    def modify_table(self, table_html):
        """拆分 table 成两个，并返回其html"""
        table = pandas.read_html(table_html, thousands="ª", decimal="ª")[0]

        # 删除最后一行
        table.drop(table.tail(1).index, inplace=True)

        # 修改型号名称
        table.loc[0, 0] = 'Product ID'

        split_num = 12

        # 获取前12行成一个表
        table1 = table.head(split_num)  # 获取n行之前
        table1_html = table1.to_html(classes='table1', header=False, index=False).replace('border="1" ', '')

        # 获取后面的行成一个表
        table2 = table.tail(len(table) - split_num)
        table2_html = table2.to_html(classes='table2', header=False, index=False).replace('border="1" ', '')

        return table1_html, table2_html

    @retry(tries=5, delay=10, backoff=2, max_delay=120)
    def fetch(self, url, timeout, headers=None):
        """
        get and post
        """
        if not isinstance(headers, dict):
            headers = dict()

        r = self.get(url, timeout, headers)
        return r

    def get(self, url, timeout, headers):
        """
        get
        """
        headers['user-agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.80 Safari/537.36 Edg/98.0.1108.50"
        return self.r.get(url=url, headers=headers, timeout=timeout, verify=False)
