import argparse
import requests
import logging
import os
import shutil
import time
from typing import Iterable, List
from urllib.parse import urljoin
from selenium import webdriver
from lxml import html as lxmlhtml
from selenium.webdriver.common.by import By
from models import Source, Webelement, Webpage, Reference
import models
import util
import envatocrawler

DATABASE_NAME = "webdesign"


def crawl_envato(driver):
    if True not in [ i[0] for i in [[s[0] == "store_url" for s in v['key']] for v in Reference.index_information().values()]]:
        Reference.create_index(keys="store_url", unique=True)
               
    templates:Iterable[envatocrawler.EnvatoTemplate] = envatocrawler.collect_envato(driver)
    for counter, template in enumerate(templates):
        reference = Reference()
        reference.additional_info = template.additions
        reference.description = template.description
        reference.similar_templates = template.similar_templates
        reference.description_orgiginal = template.description_original
        reference.titel = template.titel
        reference.tags = template.tags
        reference.store_name = "EnvatoElements"
        reference.store_url = template.store_url
        reference.title_img_bytes = template.image
        #reference.mobile = False   # TODO detect this  
        reference.demo_url = template.demo_link
        reference.save()

def get_demo_pages(driver, url)-> List[str]:
    """from givin url of some webpage, this function returns POIs of that site, such as about.html or blog.html"""
    current_url = url
    logging.info("Scannign site {} for interesting subpages".format(current_url))
    driver.get(current_url)
    page_titel = driver.title
    time.sleep(5)
    util.wait_for_document_initialised(driver)
    try: # try and refresh url in case of redirects
        current_url = driver.current_url
    except:
        pass
    # query for status codes with requsts lib, selenium does not provide that
    sess = requests.Session()
    sess.headers.update(util.EXTRA_HEADERS)
    main_page_from_requests = sess.get(current_url, timeout=31)
    if main_page_from_requests.status_code >= 400:
        raise Exception("page returned with status code > 400, skipping")
    possibly_mobile = False
    # look for hidden templates and desgins 
    html = lxmlhtml.fromstring(driver.page_source)
    iframes = html.xpath("body//div//iframe")
    # TODO find more infos about site being moble or not
    # if len(iframes) != 0 or "preview.enableds.com" in current_url:
    #     logging.warn("this template contains iframe, it may be a phone demo")
    #     possibly_mobile = True

    refs_to_do = set()
    refs = html.xpath("body//@href")
    if len(refs) != 0:
        # key : [currentcount, max]
        contains = {"index":[0,3], "home":[0,1], "blog":[0,1], 
                        "service":[0,1], "about":[0,1], "project":[0,1], "shop":[0,1]}
        not_contains = ["themeforest", "envato", "wordpress", "squarespace", "mailto", "javascript"]
        for ref in refs:
             # fiter external stuff likly not related to this site
            if not ref.startswith("http") and not ref.startswith("#"):
                 # limit to contains[][1] for every potentialy interesting page
                for key, val in contains.items():
                    if key in ref and val[0] < val[1] and True not in [a in ref for a in not_contains]: 
                        contains[key][0] = val[0]+1
                        if ref.startswith("/"): # convert_to_url
                            ref = ref.split("/", 1)[1]
                        ref =  urljoin(current_url, ref)
                        refs_to_do.add(ref)
                        break
    else: 
        refs_to_do.add(current_url)

    # fall beck when all hrefs in the body lead to nothing relevant 
    if len(refs_to_do) == 0:
        refs_to_do.add(current_url)
    return refs_to_do, page_titel, possibly_mobile


def download_references(driver):
    if True not in [ i[0] for i in [[s[0] == "url" for s in v['key']] for v in Webpage.index_information().values()]]:
                    Webpage.create_index(keys="url", unique=True)

    invalid_refs = []
    reference: Reference
    completed_references = [a.reference_id for a in Webpage.find_all(projection={"_id":0, "reference_id":1})]
    for reference in Reference.find_all():
        # skip reference that are already done
        #[a.reference_id for a in Webpage.find_all(pattern={"reference_id": reference._id}, projection={"_id":0, "reference_id":1})]:
        if reference._id in completed_references:
            continue 
        if reference.demo_url is None or len(reference.demo_url) == 0:
            reference.delete()
            continue
        try:
            urls, _titel, _ismobile = get_demo_pages(driver, reference.demo_url)
            for url in urls:
                if Webpage.find_one({"url": url}) is not None:
                    continue
                logging.info("Downloading url {} for ref_id {}".format(url, reference._id))
                try:
                    html, page_content, failed_req = util.download_page_raw(url=url)
                    if html is None:
                        invalid_refs.append({"ref_id": reference._id, "url":url, "reason": page_content})
                        logging.warning("could not get {}, code {}".format(url, page_content))
                    else:
                        webpage = Webpage()
                        webpage.url = url
                        webpage.titel = _titel 
                        #webpage.ismobile = _ismobile
                        _source = Source()
                        _source.html = html
                        _source.local_titel = "index.html"
                        _source.content = page_content
                        _source.failed_requests = failed_req
                        webpage.source = _source
                        webpage.reference_id = reference._id
                        webpage.save()
                except Exception as e:
                    invalid_refs.append({"ref_id": reference._id, "url": url, "reason": e})
                    logging.exception("unkown error while getting reference._id {} page: ".format(reference._id))
        except Exception as e:
            reference.delete()
            invalid_refs.append({"ref_id": reference._id, "url": None, "reason": e})
            logging.exception("unkown error while getting reference._id {} page: ".format(reference._id))
    print(invalid_refs)

def capture_elements(driver, client):
    page: Webpage
    for counter, page in enumerate(Webpage.find_all()):
        if counter == 10: 
            return
        if page.webelements is None or len(page.webelements) == 0:
            try:
                captures = util.capture_elements(driver=driver, url=page.url)
                for el_name, data in captures.items():
                    webelement = Webelement()
                    webelement.name = el_name
                    webelement.html = data["html"]
                    webelement.css = data["css"]
                    webelement.screenshot = data["screenshot"]
                    webelement.webpage_id = page._id
                    webelement.save()
                    page.webelements.update({el_name: webelement._id})
                    page.save()
            except Exception as e: 
                logging.exception("unkown error while getting screenshots for id {}, url {}".format(page.url, page._id))

def save_on_disc(download_path):
    page: Webpage
    for counter, page in enumerate(Webpage.find_all()):
        if counter == 10: 
            return
        try:
            path = os.path.join(download_path, str(page._id))
            # screenshots_path = os.path.join(path, "screenshots")
            # os.makedirs(screenshots_path, exist_ok=True)
            source_path = os.path.join(path, "source")
            os.makedirs(source_path, exist_ok=True)
            with open(os.path.join(source_path, page.source.local_titel), "wb") as f:
                if type(page.source.html) != bytes:
                    data = page.source.html.encode()
                else:
                    data = page.source.html
                f.write(data) 
            for key, val in page.source.content.items():
                os.makedirs(os.path.dirname(os.path.join(source_path, key)), exist_ok=True)
                with open(os.path.join(source_path, key), "wb") as f:
                    f.write(val) 

            webelements_path = os.path.join(path, "webelements")
            os.makedirs(webelements_path, exist_ok=True)
            for key, val in page.webelements.items():
                os.makedirs(os.path.dirname(os.path.join(webelements_path, key)), exist_ok=True)
                webelement:Webelement = Webelement.find_by_id(val)
                with open(os.path.join(webelements_path, key + ".png"), "wb") as f:
                    f.write(webelement.screenshot) 

            # TODO rework persistenzlayer with GridFS
            # if page.screenshots is not None:                      
            #     for key, val in page.screenshots.items():
            #         screenshot = Screenshot.find_by_obj_id(val)
            #         with open(os.path.join(path, key), "wb") as f:
            #             f.write(screenshot.data)     
        except Exception as e:
            logging.exception("unkown error while page to disc for {}".format(page.url))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Collect websamples from Envato')
    parser.add_argument('--crawl_envato', action='store_true',
                        help="Signal to collect website links Envato Element store")
    parser.add_argument('--download', action='store_true', 
                        help="Signal to download webpages from references and store them in the database")
    parser.add_argument('--screenshot', action='store_true',
                        help="Take extra Fullpage screenshots from stored webpages")
    parser.add_argument('--capture', action='store_true',
                        help="Signal to download webelements from webpages and store them in the database")
    #parser.add_argument('--zip_page', action='store_true')
    parser.add_argument('--save_on_disc', action='store_false', 
                        help="Extract webpages and save them onto disc to display them locally")
    #parser.add_argument('--analyse', action='store_true')
    parser.add_argument('--database_server', type=str, nargs=1, 
                        help='mongodb connection string, default="mongodb://localhost:27017/"', 
                        default="mongodb://localhost:27017/")
    parser.add_argument('--download_path', type=str, nargs=1,
                        help='Stores webcontent and metadata under that folder, default="D:/swipedata"', 
                        default="D:/swipedata")
    parser.add_argument('--headless', action='store_true', 
                        help='No gui for Chrome (WARN: disables full body screenshots!)')
    parser.add_argument('--height', type=int, nargs=1, 
                        help='window size (relevant for screenshots), default=1920', default=1920)
    parser.add_argument('--width', type=int, nargs=1, 
                        help='window size (relevant for screenshots), default=1080', default=1080)
    parser.add_argument('--path_chrome_driver', type=str, nargs=1, 
                        help='path to chrome driver (note that chrome needs to be installed on the os), default="tools/chromedriver.exe"', 
                        default='tools/chromedriver.exe')
    parser.add_argument('--path_chrome_extensions', type=str, nargs='*', 
                        help='path strings to chrome extensions (ctx archive) that should be loaded, default=["tools/I-don-t-care-about-cookies.crx"]', 
                        default=['tools/I-don-t-care-about-cookies.crx'])
    logging.basicConfig()
    logging.getLogger().setLevel(logging.INFO)
    args = parser.parse_args()
    print(args)
    
    chrome_op = webdriver.ChromeOptions()
    for ex_path in args.path_chrome_extensions:
        chrome_op.add_extension(ex_path)
    chrome_op.add_argument("--window-size={},{}".format(args.height, args.width))
    if args.headless:
        logging.warn("This disables page download via browser gui")
        chrome_op.add_argument("--headless")
    
    # TODO seperate browser related stuff from the rest that does not need it 
    #   -> prob major refactoring (two seperate scripts or something)
    with util.init_webdriver(args.path_chrome_driver, chrome_op) as driver:
        with models.mongodb_connection(args.database_server, DATABASE_NAME) as client:

            if args.crawl_envato:
                crawl_envato(driver)

            if args.download:
                download_references(driver)
            
            # if args.screenshot:
            #     extended_screenshot = util.take_screenshot_via_cdp_cmd(driver, args.width)
            #     screenshot = util.take_screenshot_via_cdp_cmd(driver, args.width, args.height)

            if args.capture:
                capture_elements(driver, client)

            if args.save_on_disc:
                save_on_disc(args.download_path)
                
            # if args.zip_page:
            #     page: Webpage
            #     for counter, page in enumerate(Webpage.find_all()):
            #         try:
            #             pass
            #         except Exception as e:
            #             logging.exception("unkown error while getting zipping page for id {}, url {}".format(page.url, page._id))

            # if args.analyse:
            #     pass


            