import json
import os
import re
import time

import requests
import magic
from retry import retry
from loguru import logger
from requests_toolbelt.multipart.encoder import MultipartEncoder

_feature_picture_id = ''  # wp 特色图片


class Api:
    def __init__(self):
        self.my_domain = 'https://products.com'
        self.post_api_url = self.my_domain + '/wp-json/wp/v2/posts'
        self.category_api_url = self.my_domain + '/wp-json/wp/v2/categories'
        self.img_api_url = self.my_domain + '/wp-json/wp/v2/media'

    def check_product_id(self, product_id):
        """
        用id检查 product 是否存在
        :param product_id:
        :return:
        """
        r = requests.get(f'{self.my_domain}/product_Api.php?product_id={product_id}')

    def post_article(self, title, content, category_id):
        """
        使用 wordpress rest api 发布文章
        :param category_id:
        :param title:
        :param content:
        :return: bool
        """
        global _feature_picture_id
        _feature_picture_id = ''  # 清空特殊图片

        if not title or not content:
            logger.error('Title or content is empty')
            return

        def img_callback(m):
            """正则取图片链接，替换成上传到WP后的"""
            old_url = m.group(1)
            if not old_url:
                return old_url

            pic_id, new_url = self.upload_picture(old_url, title)
            if not pic_id:
                # 图片没传成功，依然使用原图链接
                return old_url

            # 设置特色图片
            global _feature_picture_id
            if not _feature_picture_id:
                _feature_picture_id = pic_id

            new_code = f'<img src="{new_url}"'
            return new_code

        # 正则提取所有图片并上传到 wp，替换游侠图片为 wordpress 图片
        final_content = re.sub(r'<img[\s\S]+?src=[\'\"](.+?)[\'\"][\s\S\>]?', img_callback, content)

        try:
            status = self.submit(title, final_content, _feature_picture_id, category_id)  # 提交文章
        except Exception as e:
            logger.error(f'Submit {title} failed: {e}')
            return

        return status

    def upload_picture(self, img_url, title):
        """ 从游侠下载图片，然后上传到wp"""
        try:
            r_download = self.fetch(img_url)
        except Exception as e:
            logger.error(f'Download {img_url} failed: {e}')
            return "", ""

        if r_download.status_code != 200:
            logger.error(f'Download {img_url} failed: {r_download.status_code}')
            return "", ""

        file_name = f'scrape_{str(round(time.time() * 1000))}.{os.path.splitext(img_url)[-1][1:]}'

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

        logger.debug(f"Download: {url}")

        r = requests.get(url, headers=header, timeout=45, allow_redirects=False)

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
                'caption': title,
            }
        )

        r_upload = requests.post(self.img_api_url,
                                 data=multipart_data,
                                 headers={'Content-Type': multipart_data.content_type},
                                 auth=(setting.WP_USER_ID, setting.WP_API_KEY))
        return r_upload

    @retry(tries=8, delay=1, backoff=2)
    def submit(self, title, content, feature_id, category_id):
        """发布文章到wp"""
        logger.debug(f"Submit Article: {title}")

        payload = {
            'title': title,
            'content': content,
            'status': "publish",
            'author': "1",
            'categories': category_id,
            'featured_media': feature_id
        }

        headers = {'content-type': "Application/json"}

        r = requests.post(self.post_api_url,
                          data=json.dumps(payload),
                          headers=headers,
                          auth=(setting.WP_USER_ID, setting.WP_API_KEY)
                          )
        if r.status_code == 201:
            logger.debug(f'Submit success: {r.status_code}')
            return True
        else:
            logger.error(f'Submit failed: {r.status_code}')
            return False

    @retry(tries=5, delay=1, backoff=2)
    def create_category(self, game_name):
        """插件栏目"""
        payload = {
            'name': game_name,
            # 'parent': setting.PARENT_CATEGORY_ID,
        }

        headers = {'content-type': "Application/json"}

        r = requests.post(self.category_api_url,
                          data=json.dumps(payload),
                          headers=headers,
                          auth=(setting.WP_USER_ID, setting.WP_API_KEY)
                          )
        if r.status_code == 201:
            logger.debug(f'Create success: {r.status_code}')
            return r.json()['id']
        else:
            if r.status_code == 400:
                if 'term_exists' in r.text:
                    logger.warning(f'{game_name} category exists')
                    return r.json()['data']['term_id']

            logger.error(f'Create failed: {r.status_code}')
            return False
