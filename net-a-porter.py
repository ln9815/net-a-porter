import requests
from bs4 import BeautifulSoup
import os,sys,time,logging,re
from pymongo import MongoClient
from multiprocessing import Pool
from multiprocessing.dummy import Pool as ThreadPool
from multiprocessing.dummy import Lock
import glob,shutil,datetime
from tqdm import tqdm,trange
import configparser

class NAPGetter:    
    max_thread=100
    max_retry=5
    time_sleep=2
    save_loc=''
    pbar1=None
    pbar3=None
    def __init__(self, save_loc,max_thread=100, max_retry=5, time_sleep=2):
        self.max_thread=max_thread
        self.max_retry=max_retry
        self.time_sleep=time_sleep
        self.save_loc=save_loc
        pbar1=None
        pbar3=None
    

    #
    # 查找文件下满足匹配条件的所有文件
    #
    def findfiles(self,dirname,pattern):
        if os.path.exists(dirname) :
            cwd = os.getcwd() #保存当前工作目录
            os.chdir(dirname)

            result = []
            for filename in glob.iglob(pattern): #此处可以用glob.glob(pattern) 返回所有结果
                result.append(filename)

            #恢复工作目录
            os.chdir(cwd)
            return result
        else:
            return None


    #
    #获取服装相关的所有品牌
    #
    #Reutn: Barnds
    #
    def getBrands(self):

        logging.debug("Enter module: %s",sys._getframe().f_code.co_name)
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.89 Safari/537.36'}
        url="https://www.net-a-porter.com/Shop/AZDesigners?category=30"

        try:
            res=requests.get(url,headers=headers)
            res.encoding="utf-8"
            #print("获取网站的服装品牌清单.",url,res.status_code)

            if res.status_code==200:
                soup=BeautifulSoup(res.text,"html.parser")
                links=soup.select(".designer_list_col ul a")


                brands=[]
                for link in links:
                    if link.get("title") !=None and link.get("href") !=None :
                        brand= dict(BrandID=len(brands) + 1,
                                    BrandName=re.sub(r"[^0-9a-zA-Z ]","",link.get("title")),
                                    href="https://www.net-a-porter.com"+link["href"])
                        logging.debug("成功获取第%d个品牌%s,HREF=%s",brand["BrandID"],brand["BrandName"],brand["href"])
                        brands.append(brand)

                logging.debug("Leaving module: %s",sys._getframe().f_code.co_name)
                return brands

        except:
            #print("获取网站的服装品牌清单失败.:",url)
            logging.error("获取网站的服装品牌清单失败.")
            time.sleep(self.time_sleep)
            return self.getBrands()

    #
    # 获取该品牌下的产品列表
    #return: 产品列表
    #
    def getProducts(self,brand,reTry=0):
        logging.debug("Enter module: %s",sys._getframe().f_code.co_name)
        headers={
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.89 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'zh-CN,zh;q=0.9'}

        try:
            res=requests.get(brand["href"],headers=headers,timeout=10)
            res.encoding="utf-8"

            if res.status_code==200:
                soup=BeautifulSoup(res.text,"html.parser")
                links=soup.select("img[data-image-product]")

                products=[]
                for link in links:
                    patt=re.compile(r".*/products/(.*)/.*",re.I)
                    product=dict(SN=len(products),ProductID=re.match(patt,link["data-image-outfit"]).group(1),BrandName=brand["BrandName"],saveLoc="")
                    products.append(product)


                #print("成功获取品牌",brand["BrandName"],"下的产品清单",brand["href"])
                logging.debug("成功获取品牌%s下产品清单. %s",brand["BrandName"],brand["href"])
                logging.debug('Leaving module: %s', sys._getframe().f_code.co_name)
                self.updateBrandProgress()
                return products

        except:
            if reTry<self.max_retry:
                logging.warning("获取品牌%s下产品清单失败,现在重试. %s",brand["BrandName"],brand["href"])
                time.sleep(self.time_sleep)
                return self.getProducts(brand,reTry+1)
            else:
                logging.error("达到最大重试次数 %d，不再重新获取.产品编码:%s,产品链接：%s",reTry,product["saveLoc"],url)
                return None

    #
    # 获取产品的高清图片，保存到本地
    #
    def getImg(self,product,reTry=0):
        url="https://www.net-a-porter.com/cn/zh/product/"+product["ProductID"]+"/"

        saveLoc= product['saveLoc'] + "\\"+ product["BrandName"]
        os.makedirs(saveLoc,exist_ok=True)

        try:
            res=requests.get(url,timeout=10)
            res.encoding="utf-8"
            #print(res.status_code,url)

            if res.status_code==200:
                soup=BeautifulSoup(res.text,"html.parser")

                #判断是否sold out,
                #print(url,len(soup.select(".sold-out-details")),len(soup.select(".product-image")))
                if len(soup.select(".sold-out-details")) >0:
                    #print("产品",product["ProductID"],"已经下架，无法获取高清图片.产品详情链接：",url)
                    logging.warning("产品%s已经下架，无法获取图片.产品链接：%s",product["ProductID"],url)
                    self.updateProductProgress()
                    return 'SOLD OUT'
                else:
                    links=soup.select(".product-image")

                    for img in links:
                        urlImg="https:"+re.sub(r"[0-9a-zA-Z][0-9a-zA-Z]\.jpg$","xl.jpg",img["src"])
                        fileImg=re.match(re.compile(r".*/(.*?)$",re.IGNORECASE),urlImg).group(1)
                        filename=saveLoc+"\\"+fileImg


                        if not os.path.exists(filename):
                            res=requests.get(urlImg,timeout=120)
                            if res.status_code==200:
                                fo=open(filename,"wb")
                                fo.write(res.content)
                                fo.close()

                                #拷贝文件到更新目录
                                destFoler= product['saveLoc'] + "\\@" + time.strftime("%Y%m%d", time.localtime())  
                                destFile= destFoler  + "\\" + product["BrandName"] + "_" +fileImg
                                #print(destFoler,fileImg,destFile)
                                os.makedirs(destFoler,exist_ok=True)
                                shutil.copyfile(filename, destFile)

                                #print("图片获取成功：",urlImg,product["saveLoc"])
                                logging.info("图片获取成功: %s, 保存在 %s",urlImg,filename)

                            else:
                                #print("图片获取失败:",urlImg,product["saveLoc"])
                                logging.info("图片获取失败，图片链接: %s",urlImg)
                    
                    logging.info("产品: %s 的图片获取完成。 %s",product["ProductID"],url)
                    self.updateProductProgress()
                    return 'SUCCESS'

            elif res.status_code==404:
                logging.warning("网站没有该产品信息：%s，产品链接：%s",product["ProductID"],url)
                self.updateProductProgress()
                return 'NOT EXIST'
            else:
                if reTry<self.max_retry: 
                    logging.error("第%d次重新获取图片错误，尝试重新获取.产品编码：%s,产品链接：%s",reTry,product["saveLoc"],url)
                    time.sleep(self.time_sleep)
                    return self.getImg(product,reTry+1)
                else:
                    logging.error("达到最大重试次数 %d，不再重新获取.产品编码:%s,产品链接：%s",reTry,product["saveLoc"],url)
                    return 'FAILED'

        except:
            if reTry<self.max_retry: 
                logging.error("第%d次重新获取图片错误，尝试重新获取.产品编码：%s,产品链接：%s",reTry,product["saveLoc"],url)
                time.sleep(self.time_sleep)
                return self.getImg(product,reTry+1)
            else:
                logging.error("达到最大重试次数 %d，不再重新获取.产品编码:%s,产品链接：%s",reTry,product["saveLoc"],url)
                return 'FAILED'

   
    def updateBrandProgress(self,lock=None):    
        if lock is not None:
            lock.acquire()
            self.pbar1.update(1)
            lock.release()
        else:
            self.pbar1.update(1)
            

    def updateProductProgress(self,lock=None):   
        if lock is not None:
            lock.acquire()
            self.pbar3.update(1)
            lock.release()
        else:
            self.pbar3.update(1)
                    
                    
    def run(self):
        imgPath=self.save_loc
        MAX_THREAD=self.max_thread
        if not os.path.isdir(imgPath):
            os.makedirs(imgPath,exist_ok=True)

        #
        #获取网站下服装品类的所有品牌
        #
        brands=self.getBrands()
        print('\n从网站查询到共有{}个服装品牌.'.format(len(brands)))
        logging.info("从网站查询到共有%s个服装品牌.",len(brands))
        
        
        #
        #启动多线程，获取各个品牌下的产品信息
        #
        print('\n启动多线程获取各个品牌下的产品信息{0}'.format("-"*20))
        logging.debug('{0}启动多线程获取各个品牌下的产品信息{0}'.format("-"*20))
        self.pbar1 = tqdm(total=len(brands),ncols =0,desc="获取品牌产品清单进展")
        lock=Lock()
        #p=Pool(processes=min(len(brands),20))
        p=ThreadPool(processes=min(len(brands),MAX_THREAD))
        res=p.map(self.getProducts,brands)
        self.pbar1.close()    
        #合并多线程返回的产品信息为一个List
        products=[]
        for item in res:
            products.extend(item)
        print("查询该网站共有{}个产品.".format(len(products)))
        logging.info("查询该网站共有{}个产品.".format(len(products)))
        
        
        #
        #查找是否已经存在这产品的图片,并更新List中各个产品的保存地址
        #    
        print('\n检查有多少产品需要从网站更新获取{0}'.format("-"*20))
        logging.debug('{0}检查有多少产品需要从网站更新获取{0}'.format("-"*20))
        global pbar2
        pbar2 = tqdm(total=len(products),ncols =0,desc="计算需新获取图片进展")
        newProducts=[]
        for product in products:
            folder=imgPath + "\\"+ product["BrandName"]
            file=product["ProductID"]+"*.jpg"
            existImgs=self.findfiles(folder,file)
            if existImgs is None or len(existImgs)<1:
                    product["saveLoc"]=imgPath
                    #print(file,folder,product)
                    newProducts.append(product)
            pbar2.update(1)
        pbar2.close()
        print("检查识别共有{}个新产品，需从网站下载.".format(len(newProducts)))
        logging.info("检查识别共有{}个新产品，需从网站下载.".format(len(newProducts)))
        
        
        print('\n从网站开始获取产品图片{0}'.format("-"*20))
        logging.debug('{0}从网站开始获取产品图片{0}'.format("-"*20))        
        self.pbar3 = tqdm(total=len(newProducts),ncols =0,desc="获取产品图片进展：")
        #
        # 启动多线程，获取各个产品的图片
        #
        #p=Pool(processes=min(len(products),20))
        p=ThreadPool(processes=min(len(newProducts),MAX_THREAD))
        imgRes=p.map(self.getImg,newProducts)
        self.pbar3.close()
        print('获取完成完成。 已下载:{}, 失败:{},下架:{}, 失效:{}'.format(imgRes.count('SUCCESS'),imgRes.count('FAILED'),imgRes.count('SOLD OUT'),imgRes.count('NOT EXIST')))
        logging.debug('获取完成完成。 已下载:{}, 失败:{},下架:{}, 失效:{}'.format(imgRes.count('SUCCESS'),imgRes.count('FAILED'),imgRes.count('SOLD OUT'),imgRes.count('NOT EXIST')))



if __name__=="__main__":
    imgPath="D:\\NET-A-PORTER"
    
    
    
    #解析配置文件
    config = configparser.ConfigParser()
    config.read('NAP.config')    
    #config.read('test.config')
    #print(log_level,log_level[config['DEFAULT']['loglevel']])
    log_level=config['Log']['loglevel']
    filename=config['Log']['filename']
    save_loc=config['DEFAULT']['save_loc']
    max_thread=config['DEFAULT']['max_thread']
    max_retry=config['DEFAULT']['max_retry']
    time_sleep=config['DEFAULT']['time_sleep']
    
    print('获取配置文件信息如下：\n日志级别:{}\n日志文件:{}\n图片存储位置:{}\n最大线程数量:{}\n最大重试次数:{}\n等待时间:{}.'.format(log_level,filename,save_loc,max_thread,max_retry,time_sleep))
    
    
    level=dict(DEBUG=logging.DEBUG,
                    INFO=logging.INFO,
                    WARNING=logging.WARNING,
                    ERROR=logging.ERROR,
                    CRITICAL=logging.CRITICAL)
    #设置日志级别
    format='%(asctime)s %(levelname)s:  %(message)s'
    logging.basicConfig(filename=filename,level=level[log_level],format=format)
    
    #print(config,config.sections(),config['DEFAULT']['MAX_RETRY'])
        

    logging.debug("%s%s%s","-"*50,"开始从Net-A-Porter网站获取最新服装图片","-"*50)
    #RetriveNAP(imgPath)
    #getAllProduct(imgPath)
    #npa=NAPGetter(save_loc=config['DEFAULT']['sava_loc'],max_thread=config['DEFAULT']['max_thread'],max_retry=config['DEFAULT']['max_retry'],,time_sleep=config['DEFAULT']['time_sleep'])
    nap=NAPGetter(save_loc)
    nap.run()
    logging.debug("%s%s%s","-"*50,"从Net-A-Porter网站获取图片完成.","-"*50)
