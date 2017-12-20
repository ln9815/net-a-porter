"""
intent: 从网站www.fwrd.com网站爬取各个品牌的图片
author: mingxiangy@126.com
"""

import glob
import sys
import os
import re
import time
import logging
from multiprocessing.dummy import Pool, Lock
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm, trange

MAX_RETRY = 100
TIME_OUT = 120

def getbrands(ntry=1):
    """
    网站所有的品牌列表
    """
    url = "http://www.fwrd.com/designers/?navsrc=main"

    try:
        res = requests.get(url, timeout=TIME_OUT)
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select(".designers_list__col li a")
        brands = []
        for link in links:
            brand = dict(name=link.text.strip(),
                         href=link.get("href"),
                         site="http://www.fwrd.com")
            brands.append(brand)
        return brands
    except:
        logging.warning("exception occured: %s", sys.exc_info()[0])
        if ntry < MAX_RETRY:
            logging.warning("%d times retry get retrive the brand list %s.", ntry, url)
            return getbrands(ntry+1)



def getproducts(brand, ntry=1):
    """
    根据品牌查询该旗下的商品列表
    """
    url = "http://www.fwrd.com/brand-alexachung/9d4b7b/"
    url = brand["site"] + brand["href"]

    try:
        res = requests.get(url, timeout=TIME_OUT)
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select(".product.grid__col.u-center")

        products = []
        for link in links:
            product = parseproduct(link.prettify())
            if product is not None:
                product["product_href"] = brand["site"] + product["product_href"]
                products.append(product)

        #更新进度条
        lock.acquire()
        pbrand.update(1)
        lock.release()

        return products
    except:
        logging.warning("exception occured: %s", sys.exc_info()[0])
        if ntry < 5:
            logging.warning("%d times retry get retrive the product list of brand: %s.", ntry, brand["href"])
            return getproducts(brand, ntry+1)
        else:
            print("finally error in getproducts.")


def parseproduct(content):
    """
    根据输入的内容，解析产品链接，品牌名称，商品名称
    """
    patt = re.compile(r".*href=\"(.*?)\".*u-margin-b--sm\">(.*?)</div.*u-margin-b--xs\">(.*?)</div>.*product__price\">(.*?)</div>.*", re.IGNORECASE|re.DOTALL|re.MULTILINE)
    patt = re.compile(r".*href=\"(.*?)\".*u-margin-b--sm\">(.*?)</div.*u-margin-b--xs\">(.*?)</div>.*", re.IGNORECASE|re.DOTALL|re.MULTILINE)
    res = re.match(patt, content)
    if res:
        return dict(product_href=res.group(1).strip(),
                    brand_name=res.group(2).strip(),
                    product_name=res.group(3).strip())
    return None


def getimagelist(product, ntry=1):
    """
    获取该产品的高清图片
    """
    url = "http://www.fwrd.com/product-trouble-t/AUNF-WS1/?d=Womens&itrownum=7&itcurrpage=1&itview=01&list=plp-list-0"
    url = product["product_href"]

    try:
        res = requests.get(url, timeout=TIME_OUT)
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.select(".product_zoom .cycle-slideshow img")

        images = []
        for link in links:
            img = dict(brand_name=product["brand_name"],
                       product_name=product["product_name"],
                       img_href=link["src"])
            images.append(img)
        return images
    except:
        logging.warning("exception occured: %s", sys.exc_info()[0])
        if ntry < MAX_RETRY:
            logging.warning("%d times retry get retrive the product image list: %s.", ntry, product["product_href"])
            return getimagelist(product, ntry+1)
        else:
            print("finally error in getimagelist.")


def retrieveimg(product, ntry=1):
    """
    从网站下载图片并保存
    """

    try:
        imgs = getimagelist(product)

        for img in imgs:
            img_loc = product["save_loc"] + "\\"+ img["brand_name"]
            os.makedirs(img_loc, exist_ok=True)
            filename = re.match(re.compile(r".*/(.*?)$", re.IGNORECASE), img["img_href"]).group(1)
            res = requests.get(img["img_href"], timeout=TIME_OUT)
            file = open(img_loc + "\\" + filename, "wb")
            file.write(res.content)
            file.close()

        #所有图片获取成功，追加写入到文件日志,更新进度条
        logging.debug("产品%s 图片获取成功。", product["product_href"])

        #更新进度条，保存已存的文件记录
        lock.acquire()
        file2 = open(product["save_loc"] + "\\saved_products.rec", "a")
        file2.writelines(product["product_href"] + "\n")
        file2.close()

        pbar.update(1)
        lock.release()
    except:
        logging.warning("exception occured: %s", sys.exc_info()[0])
        if ntry < MAX_RETRY:
            logging.warning("%d times retry get retrive the product images: %s.", ntry, product["product_href"])
            retrieveimg(product, ntry+1)
        else:
            print("finally error in retrieveimg.")


def findfiles(dirname, pattern):
    """
    查找文件下满足匹配条件的所有文件
    """
    result = []
    if os.path.exists(dirname):
        cwd = os.getcwd() #保存当前工作目录
        os.chdir(dirname)
        for filename in glob.iglob(pattern): #此处可以用glob.glob(pattern) 返回所有结果
            result.append(filename)

        #恢复工作目录
        os.chdir(cwd)
    return result


def gen_img_list():
    """
    获取网站的满足条件的照片全集
    """
    SAVE_LOC = "D:\\FWRD_COM"

    MAX_THREAD = 300
    brands = getbrands()
    print("查询到共有", len(brands), "品牌！")

    #启动多线程获取所有各个品牌下的产品集合
    global pbrand
    pbrand = tqdm(total=len(brands), ncols=0, desc="获取各品牌产品目录进展：")
    pool_products = Pool(processes=min(len(brands), MAX_THREAD))
    res = pool_products.map(getproducts, brands)
    pbrand.close()

    products = []
    for item in res:
        products.extend(item)
    print("查询到共有", len(products), "产品！")


    #对比有多少产品需要重新获取
    saved_products = get_saved_products(SAVE_LOC)
    new_products = []
    for product in products:
        if saved_products.count(product["product_href"]) < 1:
            product["save_loc"] = SAVE_LOC
            new_products.append(product)
    print("其中", len(new_products), "个产品需要从网站重新获取。")

    if len(new_products) < 1:
        return

    #启动多线程获取获取并保存产品图片
    global pbar
    pbar = tqdm(total=len(new_products), ncols=0, desc="获取产品图片进展：")
    pool_saveimg = Pool(processes=min(len(new_products), MAX_THREAD))
    res = pool_saveimg.map(retrieveimg, new_products)
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


if __name__ == "__main__":
    SITE = "http://www.fwrd.com"

     #设置日志级别
    log_format = '%(asctime)s %(levelname)s:  %(message)s'
    logging.basicConfig(filename="fw.log", level=logging.INFO, format=log_format)

    lock = Lock()
    gen_img_list()
