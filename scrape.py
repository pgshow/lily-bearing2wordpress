import os
import re
import time
import wpApi
import requests
import pandas
import urllib.parse

from loguru import logger
from retry import retry
from bs4 import BeautifulSoup
from lxml import etree


class Scrape:
    def __init__(self, link):
        self.r = requests.session()
        self.wp_cls = wpApi.Api()
        self.link = link
        self.root = 'https://www.lily-bearing.com/'

    def run(self):
        logger.info(f'Scrape category {self.link}')
        # self.link = 'https://www.lily-bearing.com/slewing-ring-bearings/'
        r = self.fetch(self.link, 30)

        if r.status_code != 200:
            logger.error(f"Fetch {r.url} failed, {r.status_code}")
            return

        self.extract_category(r)

    def product_exist(self, product_id):
        """
        用id检查 product 是否存在
        :param product_id:
        :return:
        """
        url = f'https://products.com/product_Api.php?product_id={product_id}'
        # url = f'https://products.com/product_Api.php?product_id=SRMS36'
        r = self.fetch(url, 30)
        if r.status_code != 200:
            raise Exception(f"Fetch product_Api.php failed, {r.status_code}, please check your WP API")

        json_data = r.json()
        if not json_data['exist']:
            return

        category_ids = set()
        for c in json_data['exist']['categories']:
            category_ids.add(c['term_id'])

        data = {'article_id': json_data['exist']['article_id'], 'cat_ids': category_ids}

        logger.warning(f'Exist, Update Product: {product_id}')

        return data

    def extract_category(self, r):
        if r.text == "":
            return

        soup = BeautifulSoup(r.text, 'lxml')

        # 一、二级分类
        categories = []
        for nav in soup.select('div.nav-title > .layui-breadcrumb'):
            nav_items = nav.select('a')
            level1 = nav_items[1].text
            level2 = nav_items[2].text
            categories.append({
                'level1': {'name': level1},
                'level2': {'name': level2}
            })

        for sub_list in soup.select('div.boxT > .posit-box'):
            # 三级分类
            level3 = sub_list.select_one('h2 > a').text.strip()
            logger.info(f"Scrape genre: {level3}")

            # 添加三级到分类结构体
            for c in categories:
                c['level3'] = {'name': level3}

            # 获取分类id
            category_ids = self.wp_cls.build_categories(categories)

            # product urls in this sub genre
            for a in sub_list.select('div.hang > a'):
                time.sleep(1)
                try:
                    # Only update if this product already exist
                    exist_data = self.product_exist(a.select_one('div.Product').text)
                    if exist_data:
                        # union exist category with new category
                        category_ids = category_ids.union(exist_data['cat_ids'])
                        self.wp_cls.update_article(exist_data['article_id'], category_ids)
                        continue

                    path = a['href']

                    if not path:
                        continue

                    logger.info(f'Find {path}')

                    r = self.fetch(self.root + path, 30)

                    if r.status_code != 200:
                        logger.error(f"Fetch {r.url} failed, {r.status_code}")
                        continue

                    self.extract_product(category_ids, level2, r)

                except Exception as e:
                    logger.error(f'Error: {e}')
                    time.sleep(10)

    def extract_product(self, category_ids, belongs_category, r):
        if r.text == "":
            return

        soup = BeautifulSoup(r.text, 'lxml')

        # product id
        product_id = soup.select_one('cite').text
        title = f'{product_id} Bearing'

        # Category
        # main_category = soup.select_one('div.firstbreadcrumb > span > a:nth-child(3)').text

        # Small img
        small_img = soup.select_one('div.layui-col-md3.detail-img-box > img')['src']
        small_img = self.root + small_img

        # Big img
        big_img = soup.select_one('div#magnifier img')['src']
        big_img = self.root + big_img

        # Price
        price = soup.select_one('div.detail-img-box > div > div > span').text.replace('$ ', '')
        if not re.match(r'\d+', price) or float(price) == 0:
            price = 'Negotiable'

        # Get table
        table_html = str(soup.select_one('div.layui-row > div.layui-col-md4 > div.layui-col-md9 > table'))
        table = pandas.read_html(table_html, thousands="ª", decimal="ª")[0]

        # Get size
        size = self.get_size(table)

        # Get table1, table2
        table1, table2 = self.modify_table(table)

        title = f'{title} {belongs_category} {size}'.strip()

        self.wp_cls.post_article(title=title,
                                 category_ids=category_ids,
                                 product_id=product_id,
                                 small_pic_url=small_img,
                                 big_pic_url=big_img,
                                 price=price,
                                 table1=table1,
                                 table2=table2,
                                 size = size,
                                 )

    def replace_cell(self, table, old, new):
        """替换第一列单元格的文字"""
        try:
            i = table[table[0] == old].index
            table.loc[i[0], 0] = new
        except:
            pass
        return table

    def modify_table(self, table):
        """拆分 table 成两个，并返回其html"""

        # 删除最后一行
        table.drop(table.tail(1).index, inplace=True)

        # 修改型号名称
        table.loc[0, 0] = 'Bearing Model'
        table.loc[0, 1] = f'{table.iat[0, 1]} Bearing'

        # 修改表格属性名称
        changes = [
            ["System of Measurement", "Size Standards"],
            ["Ball", "Deep Groove Ball Bearing"],
            ["For Load Direction", "Load Direction"],
            ["Construction", "Number of Raceway Ring Rows"],
            ["Bore Dia", "Inner Dimension d(Ø)"],
            ["Outer Dia", "Outer Dimension D(Ø)"],
            ["Width", "Width B"],
            ["Ring Material", "Inner/Outer Ring Material"],
        ]
        for c in changes:
            table = self.replace_cell(table, c[0], c[1])

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

    def get_size(self, table):
        """
        获取 table 里面 size 的属性
        """
        key_list = [
            ['Bore diameter', 'Outside diameter', 'Width'],
            ['Bore Dia', 'Outer Dia', 'Height'],
            ['Bore Dia', 'Outer Dia', 'Width'],
            ['Inside Diameter Of Inner Ring', 'Outside Diameter Of Outer Ring', 'Height Of Overall Bearing Assembly (H)'],
            ['Roller OD', 'Bore Dia', 'Roller Width'],
            ['Bore diameter (d)', 'Outside diameter (D)', 'Nominal width'],
            ['Height M', 'Width W', 'Length L'],
            ['Maximum length', 'Nominal rail size'],
            ['Bore Dia', 'Outer Dia', 'Width'],
            ['Bore Diameter', 'Outside Diameter', 'Width'],
            ['Bore(d)', 'Cup Outer Diameter(D)', 'Bearing Width(T)'],
            ['Shoulder diameter of inner ring', 'Permissible axial displacement', 'Diameter of shaft abutment'],
            ['Bore', 'Outer Diameter', 'Outer Ring Width'],
            ['b1', 'c1', 'd']
        ]

        for keys in key_list:
            try:
                values = []
                for key in keys:
                    hit = table[table[0] == key].index
                    values.append(table.loc[hit[0], 1])

                size = '×'.join(values)
                return size
            except:
                pass

        return ''

