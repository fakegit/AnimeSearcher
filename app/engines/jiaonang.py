import json
import re
from app.models import VideoList, Video, DefaultHandler, BaseEngine
from app import logger


class Engine(BaseEngine):

    @staticmethod
    def search_one_page(name, page) -> list:
        """处理一页的数据"""
        logger.info(f'引擎 {__name__} 正在搜索: {name} (第 {page} 页)')
        result = []
        search_api = 'http://59.110.16.198/app.php/XyySearch/get_search_data'
        data = {'keyword': name, 'uid': 0, 'page': page, 'type': 1}
        resp = Engine.post(search_api, data)
        if resp.status_code != 200:
            return result
        if resp.text.startswith(u'\ufeff'):  # 解决 UTF-8 BOM 编码的问题
            resp = resp.text.encode('utf8')[3:].decode('utf8')
        resp = json.loads(resp)

        if not resp['data']:
            return result

        for item in resp['data']:
            video_list = VideoList()
            is_rubbish_flag = False  # 有些视频是有问题的,应该抛弃
            if not item['video_lists']:  # 有可能出现视频列表为空的情况
                continue
            video_list.engine = __name__
            video_list.title = item['video_subject'].strip()
            video_list.cover = item['video_image']
            video_list.desc = item['video_describe'] or '视频简介弄丢了 (/▽＼)'

            logger.info(f"引擎 {__name__} 正在处理: {video_list.title}")
            if item['video_type']:
                video_list.cat = [cat['video_type_name'] for cat in item['video_type']]
            else:
                video_list.cat = ['默认']
            for video in item['video_lists']:
                url = video['vod_id']  # 有可能出现 URL 有误的情况(迷)
                if not url.startswith('http'):
                    is_rubbish_flag = True  # 有问题的视频,标记起来

                if 'www.iqiyi.com' in url:
                    is_rubbish_flag = True  # 爱奇艺的加密算法太麻烦,暂时不解析
                elif 'youku.com' in url:
                    is_rubbish_flag = True  # 优酷视频,暂时不解析
                elif 'dilidili' in url:
                    is_rubbish_flag = True  # 嘀哩嘀哩已挂

                name = f"第 {video['video_number']} 集"
                handler = None
                if 'bilibili' in url:
                    handler = BilibiliHandler
                video_list.add_video(Video(name, url, handler))
            if not is_rubbish_flag:
                result.append(video_list)
        return result

    @staticmethod
    def search(name):
        page = 1
        result = []
        while page < 3:  # 关键字不匹配会导致服务器返回一堆不相干的结果(谜之算法)
            one_page = Engine.search_one_page(name, page)
            if not one_page:
                break
            page += 1
            result += one_page
        return result


class BilibiliHandler(DefaultHandler):
    def get_real_url(self):
        """解析哔哩哔哩的视频
        url: https://www.bilibili.com/bangumi/play/ep113157
        返回分段 flv 视频的直链 (防盗链，需设置 'Referer': 'http://www.bilibili.com/')
        """
        result = []
        logger.info(f"BilibiliHandler 正在处理: {self.raw_url}")
        html = Engine.get(self.raw_url).text
        ep_list = re.findall(r'__INITIAL_STATE__=({.*});\(', html)
        ep_list = json.loads(ep_list[0])['epList'] if ep_list else None
        if ep_list is None:
            return result
        vid = int(self.raw_url.strip('/').split('/ep')[-1])  # video id : 113157
        for video in ep_list:
            if video['id'] == vid:  # 只处理指定的视频
                api = 'https://api.bilibili.com/pgc/player/web/playurl'
                param = {'qn': 112, 'cid': video['cid'], 'otype': 'json', 'type': ''}  # quality [112, 80, 64, 32, 16]
                video_info = Engine.get(api, param).json()['result']
                result = [i['url'] for i in video_info['durl']]
        logger.info(f"BilibiliHandler return: {result}")
        return result[0]

    def set_proxy_headers(self):
        self.proxy_headers = {
            'User-Agent': 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
            'Referer': 'http://www.bilibili.com/'  # 解除哔哩哔哩防盗链限制
        }
