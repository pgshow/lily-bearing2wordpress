import json
import os
import re
import time

import requests
import magic
from retry import retry
from loguru import logger
from requests_toolbelt.multipart.encoder import MultipartEncoder

main_category_id = '0'  # 主分类ID
WP_USER_ID = 'admin'
WP_API_KEY = 'YTEI hCbP sxpI ZEnv RQLp biR3'


class Api:
    def __init__(self):
        self.my_domain = 'https://products.com'
        self.post_api_url = self.my_domain + '/wp-json/wp/v2/posts'
        self.category_api_url = self.my_domain + '/wp-json/wp/v2/categories'
        self.img_api_url = self.my_domain + '/wp-json/wp/v2/media'

    def build_categories(self, categories):
        """建立 1，2，3 级分类，并返回分类ID 的集合"""
        level3_ids = set()
        for c in categories:
            level1_id = self.create_category(c['level1']['name'], main_category_id)
            level2_id = self.create_category(c['level2']['name'], level1_id)
            # level3_id = self.create_category(c['level3']['name'], level2_id)
            # level3_ids.add(level3_id)
            level3_ids.add(level2_id)

        return level3_ids

    def post_article(self, title, category_ids, product_id, small_pic_url, big_pic_url, price, table1, table2, size):
        """
        post article
        """
        feature = self.upload_picture(small_pic_url, title)  # feature picture
        if not feature:
            logger.error(f'upload small pic: {small_pic_url} failed')
            return

        structure_pic = self.upload_picture(big_pic_url, title)  # big picture
        if not structure_pic:
            logger.error(f'upload big pic: {big_pic_url} failed')
            return

        try:
            status = self.submit(title=title,
                                 category_ids=category_ids,
                                 feature_id=feature[0],
                                 product_id=product_id,
                                 structure_pic_id=structure_pic[0],
                                 price=price,
                                 table1=table1,
                                 table2=table2,
                                 size=size,
                                 )
        except Exception as e:
            logger.error(f'Submit {title} failed: {e}')
            return

        return status

    def upload_picture(self, img_url, title):
        """ 下载图片，然后上传到wp"""
        try:
            r_download = self.fetch(img_url)
        except Exception as e:
            logger.error(f'Download {img_url} failed: {e}')
            return "", ""

        if r_download.status_code != 200:
            logger.error(f'Download {img_url} failed: {r_download.status_code}')
            return "", ""

        file_name = f'scrape_{str(round(time.time() * 1000))}.{os.path.splitext(img_url)[-1][1:]}'
        if "?" in file_name:
            file_name = re.search(r'(.+)\?', file_name).group(1)

        try:
            r_upload = self.upload(r_download, file_name, title)
        except Exception as e:
            logger.error(f'Upload {img_url} failed: {e}')
            return "", ""

        if r_upload.status_code != 201:
            logger.error(f'Upload {img_url} failed:  {r_upload.status_code}')
            return "", ""

        json_data = r_upload.json()

        return json_data['id'], json_data['source_url']

    @retry(tries=6, delay=2, backoff=2)
    def fetch(self, url):
        header = {
            'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'accept-encoding': 'gzip,deflate,br',
            'accept-language': 'zh-CN,zh;q=0.9',
            'referer': 'https://gl.ali213.net/',
            'sec-ch-ua': '"GoogleChrome";v="95","Chromium";v="95",";NotABrand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'image',
            'sec-fetch-mode': 'no-cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0(WindowsNT10.0;Win64;x64)AppleWebKit/537.36(KHTML,likeGecko)Chrome/95.0.4638.69Safari/537.36',
        }

        logger.debug(f"Fetch: {url}")

        r = requests.get(url, headers=header, timeout=45, verify=False)

        return r

    @retry(tries=8, delay=1, backoff=2)
    def upload(self, r_download, file_name, title):
        """上传图片到 wordpress """
        logger.debug(f"Upload: {file_name}")

        mime = magic.from_buffer(r_download.content[0:2048], mime=True)  # 找到文件类型
        multipart_data = MultipartEncoder(
            fields={
                # a file upload field
                'file': (file_name, r_download.content, mime),
                # plain text fields
                'title': title,
                'alt_text': title,
                'caption': title,
            }
        )

        r_upload = requests.post(self.img_api_url,
                                 data=multipart_data,
                                 headers={'Content-Type': multipart_data.content_type},
                                 auth=(WP_USER_ID, WP_API_KEY),
                                 verify=False)
        return r_upload

    @retry(tries=8, delay=1, backoff=2)
    def submit(self, title, category_ids, feature_id, product_id, structure_pic_id, price, table1, table2, size):
        """发布文章到wp"""
        logger.debug(f"Submit Article: {title}")

        cat_ids_str = ",".join([str(x) for x in category_ids])

        payload = {
            'title': title,
            'content': '',
            'status': "publish",
            'author': "1",
            'categories': cat_ids_str,
            'featured_media': feature_id,
            'metadata': {
                'product_id': product_id,
                'price': price,
                'structure_pic': structure_pic_id,
                'table1': table1,
                'table2': table2,
                'size': size,
            }
        }

        headers = {'content-type': "Application/json"}

        r = requests.post(self.post_api_url,
                          data=json.dumps(payload),
                          headers=headers,
                          auth=(WP_USER_ID, WP_API_KEY),
                          verify=False
                          )
        if r.status_code == 201:
            logger.success(f'Submit success: {r.status_code}')
            return True
        else:
            logger.error(f'Submit failed: {r.status_code}')
            return False

    @retry(tries=5, delay=1, backoff=2)
    def create_category(self, category_name, category_parent_id):
        """创建分类并返回分类ID，如果分类存在会返回分类ID"""
        payload = {
            'name': category_name,
            'parent': category_parent_id,
        }

        if not category_parent_id:
            raise Exception(f"FatherID of - {category_name} - is invalid")

        headers = {'content-type': "Application/json"}

        r = requests.post(self.category_api_url,
                          data=json.dumps(payload),
                          headers=headers,
                          auth=(WP_USER_ID, WP_API_KEY),
                          verify=False,
                          )
        if r.status_code == 201:
            logger.debug(f'Create {category_name} success: {r.status_code}')
            return r.json()['id']
        else:
            if r.status_code == 400:
                if 'term_exists' in r.text:
                    logger.warning(f'{category_name} category exists')
                    return r.json()['data']['term_id']

            logger.error(f'Create {category_name} failed: {r.status_code}')
            return False

    @retry(tries=8, delay=1, backoff=2)
    def update_article(self, article_id, category_ids):
        """更新文章分类"""
        logger.debug(f"Update Article: {article_id}")

        cat_ids_str = ",".join([str(x) for x in category_ids])

        payload = {
            'categories': cat_ids_str,
        }

        headers = {'content-type': "Application/json"}

        r = requests.post(f'{self.post_api_url}/{article_id}',
                          data=json.dumps(payload),
                          headers=headers,
                          auth=(WP_USER_ID, WP_API_KEY),
                          verify=False
                          )
        if r.status_code == 200:
            logger.success(f'Update success: {r.status_code}')
            return True
        else:
            logger.error(f'Update failed: {r.status_code}')
            return False

