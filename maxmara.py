"""
从网站获取图片
"""


import json
import glob
import sys
import os
import re
import time
import logging
from urllib.parse import urlencode
from urllib.parse import urlsplit
from multiprocessing.dummy import Pool, Lock
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm, trange


MAX_RETRY = 100
TIME_OUT = 120

def parser_catgory(retry=0):
    """
    获取网站的类别清单
    """
    url = 'https://cn.maxmara.com/'
    targets = [
        {'type':'Clothing', 'select':'.dropdown.cat-200 .sub-nav-item a'},
        {'type':'Outerwear', 'select':'.dropdown.cat-100 .sub-nav-item a'}]
    catagory = []

    try:
        res = requests.get(url, timeout=TIME_OUT)
        soup = BeautifulSoup(res.text, 'html.parser')
        for target in targets:
            items = soup.select(target['select'])
            for item in items:
                cate = dict(
                    cate_type=target['type'],
                    cate_name=item.text.strip('\n'),
                    cate_href=urlsplit(url)[0] + "://" + urlsplit(url)[1] + item['href'])
                # print(cate)
                catagory.append(cate)
        return catagory
    except:
        logging.warning("exception occured: %s in %s", sys.exc_info()[0], sys._getframe().f_code.co_name)
        if retry < MAX_RETRY:
            logging.warning("%d times try in %s", retry, sys._getframe().f_code.co_name)
            return parser_catgory(retry+1)
        else:
            logging.error("final error in %s", sys._getframe().f_code.co_name)


def parser_category_pages(category, retry=0):
    """
    """
    #判断isProductGallery的设置
    #<script type="text/javascript">	$.isProductGallery = true;</script
    # url = 'https://cn.maxmara.com/dresses/c-202'
    # url = 'https://cn.maxmara.com/abiti-sposa'
    # category['url'] = url
    """
    if($.isProductGallery) {
        options.url = "/view/GalleryProductCarouselComponentController/galleryResultsViaAjax";
        var componentIdForGallery = $("#filter-list").data("uid");
        data = $.extend(data, {uid:componentIdForGallery});
        }else{
            options.url = options.url + "/resultsViaAjax";
        }
    ajaxObj : {
        q : $("#variables").data("query-on-ready"),
        sort : $(".js-select-orderby option:selected").val(),
        numberOfPage : "0",
        categoryCode : $("#category-div").data("category"),
        numberOfClothes : $(".js-select-product-for-page option:first-child").val(),
        numberOfClothesPE : $(".js-select-product-for-page option:last-child").val(),
        scrollTop : ""
		},
    """

    data = dict(
        q=':topRated:collectionActive:true',
        sort='topRated',
        numberOfPage=0,
        # categoryCode=202,
        numberOfClothes=16,
        numberOfClothesPE=16,
        scrollTop='')
    category_pages = []

    try:
        res = requests.get(category['cate_href'], timeout=TIME_OUT)
        soup = BeautifulSoup(res.text, 'html.parser')

        is_product_gallery = re.search('isProductGallery = true', res.text, re.M|re.I)
        #print('is_product_gallery:', is_product_gallery)
        if is_product_gallery:
            url_ajax = urlsplit(category['cate_href'])[0] + "://" + urlsplit(category['cate_href'])[1] + '/view/GalleryProductCarouselComponentController/galleryResultsViaAjax?'
            data['numberOfClothes'] = soup.select('.js-select-product-for-page option:nth-of-type(1)')[0].string
            data['numberOfClothesPE'] = data['numberOfClothes']
            data['uid'] = soup.select('#filter-list')[0]['data-uid']
            total_page = 1
        else:
            url_ajax = category['cate_href'] + '/resultsViaAjax?'
            #print(url_ajax + urlencode(data))
            res = requests.get(url_ajax + urlencode(data), timeout=TIME_OUT)
            if res.status_code != 200: return category_pages
            total_page = json.loads(res.text)['totalPage'] #获取总的页数
            data['numberOfClothes'] = soup.select('.js-select-product-for-page option:nth-of-type(1)')[0].string
            data['numberOfClothesPE'] = soup.select('.js-select-product-for-page option:nth-of-type(2)')[0].string

        for i in range(total_page):
            data['numberOfPage'] = i
            url =  url_ajax + urlencode(data)
            category_page = dict(cate_type=category['cate_type'],
                                cate_name=category['cate_name'],
                                is_product_gallery=is_product_gallery,
                                page_url=url)
            #print(category_page)
            category_pages.append(category_page)
        logging.info("page info of catagory %s parsered sucessfully", category['cate_href'])
        return category_pages
    except:
        logging.warning("exception occured: %s in %s", sys.exc_info()[0], sys._getframe().f_code.co_name)
        if retry < MAX_RETRY:
            logging.warning("%d times try in %s", retry, sys._getframe().f_code.co_name)
            return parser_category_pages(category, retry+1)
        else:
            logging.error("final error in %s", sys._getframe().f_code.co_name)


def parser_products_by_page(category_page, retry=0):
    """
    获取特定目录下,某一页的产品清单，以及相应的链接
    """
    # url = 'https://cn.maxmara.com/dresses/c-202'
    # url_org = 'https://cn.maxmara.com/dresses/c-202/resultsViaAjax?q=%3AtopRated%3AcollectionActive%3Atrue&sort=topRated&numberOfPage=0&categoryCode=202&numberOfClothes=16&numberOfClothesPE=16&scrollTop=&_=1514644783063'
    # url_ajax = 'https://cn.maxmara.com/dresses/c-202/resultsViaAjax?'

    products = []
    url = category_page['page_url']
    #print(url)

    try:
        res = requests.get(url, timeout=TIME_OUT)
        content = json.loads(res.text)
        if category_page['is_product_gallery']:
            product_list=content['searchPageData']['results']
        else:
            product_list=content['searchPageData']['results'][0]['productList']

        for product in product_list:
            item = dict(
                cate_type=category_page['cate_type'],
                cate_name=category_page['cate_name'],
                save_loc='d://maxmara_img',
                product_href=urlsplit(url)[0] + "://" + urlsplit(url)[1] + product['url'])
            #print(item)
            products.append(item)

        logging.info("page info of %s parsered successfully.", url)
        return products
    except:
        logging.warning("exception occured: %s in %s", sys.exc_info()[0], sys._getframe().f_code.co_name)
        if retry < MAX_RETRY:
            logging.warning("%d times try in %s", retry, sys._getframe().f_code.co_name)
            return parser_products_by_page(category_page, retry+1)
        else:
            logging.error("final error in %s", sys._getframe().f_code.co_name)

def retrieve_img(product,retry=0):
    url = 'https://cn.maxmara.com/p-9226077906001-arturo-beige'
    url = 'https://cn.maxmara.com/p-9226077906001-arturo-beige/ajax?_=1514646365123'
    url = product['product_href'] + '/ajax?'


    # img_loc = product["save_loc"] + "\\"+ img["brand_name"]
    os.makedirs(product['save_loc'], exist_ok=True)


    try:
        res = requests.get(url, timeout=TIME_OUT)
        content = json.loads(res.text)
        images = content['images']

        #去除重复的图片
        images_url = []
        for image in images:
            if images_url.count(image['url']) < 1:
                images_url.append(image['url'])
            else:
                images.remove(image)

        #只获取大尺寸图片并保存
        for image in images:
            if image['format'] == 'zoom':
                #print(image['url'])
                filename = re.match(re.compile(r".*/(.*?)$", re.IGNORECASE), image['url']).group(1)
                res = requests.get(image['url'], timeout=TIME_OUT)
                file = open(product['save_loc'] + "\\" + filename, "wb")
                file.write(res.content)
                file.close()
                #print(filename, "saved successfully")
                logging.info("%s saved successfully", image['url'])

        #保存已存的文件记录
        write_saved_products(product['save_loc'], product['product_href'])
        logging.info("product of %s saved completed.", product['product_href'])
        if 'bar' in product:
            product['bar'].update(1)

    except:
        logging.warning("exception occured: %s in %s", sys.exc_info()[0], sys._getframe().f_code.co_name)
        if retry < MAX_RETRY:
            logging.warning("%d times try in %s", retry, sys._getframe().f_code.co_name)
            return retrieve_img(product, retry+1)
        else:
            logging.error("final error in %s", sys._getframe().f_code.co_name)

def main():
    """
    主程序
    """
    MAX_THREAD = 300
    SAVE_LOC = 'd://maxmara_img'
    MULTI_THREAD = True

    #设置日志级别
    log_format = '%(asctime)s %(levelname)s:  %(message)s'
    logging.basicConfig(filename="mm.log", level=logging.INFO, format=log_format)


    #获取网站总目录
    categories = parser_catgory()
    print("查询到共有", len(categories), "产品类别！")

    #查询产品分页的地址
    limit = None
    if limit:
        num=min(limit,len(categories))
    else:
        num=len(categories)
    category_pages = []
    if MULTI_THREAD:
        tpool = Pool(processes=min(num, MAX_THREAD))
        res = tpool.map(parser_category_pages,categories[:num])
        category_pages = merge_res(res)
    else:
        for category in categories[:num]:
            category_page = parser_category_pages(category)
            category_pages.extend(category_page)
    print("查询到共有", len(category_pages), "产品目录页面！")

    #查询产品信息
    limit = None
    if limit:
        num=min(limit,len(category_pages))
    else:
        num=len(category_pages)
    product_list = []
    if MULTI_THREAD:
        tpool = Pool(processes=min(num, MAX_THREAD))
        res = tpool.map(parser_products_by_page,category_pages[:num])
        product_list = merge_res(res)
    else:
        for category_page in category_pages[:num]:
            products = parser_products_by_page(category_page)
            product_list.extend(products)
    print("查询到共有", len(product_list), "产品！")

    #查询有多少产品需要重新获取
    saved_products = get_saved_products(SAVE_LOC)
    new_products = []
    for product in product_list:
        if saved_products.count(product['product_href']) < 1:
            product["save_loc"] = SAVE_LOC
            new_products.append(product)
    print("其中", len(new_products), "个产品需要从网站重新获取。")

    if len(new_products) < 1:
        return



    #获取产品图片,并更新进度跳
    limit = None
    if limit:
        num=min(limit,len(new_products))
    else:
        num=len(new_products)
    pbar = tqdm(total=len(new_products), ncols=0, desc="获取产品图片进展：")
    if MULTI_THREAD:
        for product in new_products:
            product['bar'] = pbar
        tpool = Pool(processes=min(num, MAX_THREAD))
        res = tpool.map(retrieve_img,new_products[:num])
    else:
        for product in new_products[:num]:
            pbar.update(1)
            retrieve_img(product)
    pbar.close()

def get_saved_products(save_loc):
    """
    读取文件，获取已经保存的产品列表
    """
    file = open(save_loc + "\\saved_products.rec", "r")
    rec = []
    while 1:
        line = file.readline()
        if not line:
            break
        rec.append(line.strip('\n'))
    return rec

def write_saved_products(save_loc, url):
    file = open(save_loc + "\\saved_products.rec", "a")
    file.writelines(url + "\n")
    file.close()


def merge_res(res):
    new_list = []
    for item in res:
        new_list.extend(item)
    return new_list


def get_host(url):
    """
    根据URL获取相应网站主机地址
    """
    return urlsplit(url)[0] + "://" + urlsplit(url)[1]

def run(bar):
    for i in range(100):
        bar.update(1)
        time.sleep(1)
def test():
    pbar = tqdm(total=100, ncols=0, desc="progress:")
    run(pbar)
    pbar.close()

if __name__ == "__main__":
    main()
