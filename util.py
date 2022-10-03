import contextlib
import logging
import random
from typing import Any, Dict, List, Set, Tuple, Union
import requests
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
import selenium.webdriver.common.devtools.v102 as devtools
from lxml import html as lxmlhtml
import base64
import os
import pyautogui
import time
import re as regex
from urllib.parse import urlsplit, urljoin
import cv2
import numpy as np

EXTRA_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "*",
    "Dnt": "1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0'
}


def DELAY(): return random.uniform(3, 12)


def wait_for_document_initialised(driver: WebDriver, timeout: int = 15):
    return WebDriverWait(driver, 10).until(lambda x: x.execute_script("return 1"))


def check_if_window_present(driver: WebDriver):
    return True if driver.execute_script("if(window.chrome) {return 42} else {return 0}") == 42 else False


global _downloads_window_handle
_downloads_window_handle = None
def wait_for_downloads(driver: WebDriver):
    """check if downloads are stil running inside chrome. returns after downloads are finished."""
    old_window = driver.current_window_handle
    # if len(driver.window_handles) != 1 :
    global _downloads_window_handle
    if _downloads_window_handle is None:
        driver.switch_to.new_window('tab')
        _downloads_window_handle = driver.current_window_handle
    else:
        driver.switch_to.window(_downloads_window_handle)

    if not driver.current_url.startswith("chrome://downloads"):
        driver.get("chrome://downloads/")

    ret = []
    while True:
        time.sleep(1)
        ret = driver.execute_script("""
            return document.querySelector('downloads-manager')
            .shadowRoot.querySelector('#downloadsList')
            .items.filter(e => e.state === 'IN_PROGRESS')
            .map(e => e.filePath);
            """)
        if len(ret) == 0:
            break
    driver.switch_to.window(old_window)
    pass


global _web_driver_running
_web_driver_running = False


@contextlib.contextmanager
def init_webdriver(path, op) -> WebDriver:
    global _web_driver_running
    if _web_driver_running:
        raise RuntimeError("you should not have more than one driver running")
    dc = DesiredCapabilities.CHROME
    # to be able to get chrome console output
    dc['goog:loggingPrefs'] = {'browser': 'ALL'}
    try:
        driver: WebDriver = webdriver.Chrome(
            executable_path=path, options=op, desired_capabilities=dc)
        driver.minimize_window()
        driver.maximize_window()
        _web_driver_running = True
        yield driver
        wait_for_downloads(driver)
    finally:
        _web_driver_running = False
        global _downloads_window_handle
        if _downloads_window_handle:
            _downloads_window_handle = None
        driver.close()
        driver.quit()


def analyse_browser_logs_for_errors(driver: WebDriver) -> bool:
    """scans logs for errors, returns true if erros were found"""
    for entry in driver.get_log('browser'):
        if entry.level == "SEVERE":
            return True
        # print(entry.level) # can be 'SEVERE''INFO': other: ALL, DEBUG, INFO, WARNING, SEVERE, and OFF
        # print(entry.message) # ususaly some like this: https://./index_files///www.google-analytics.com/analytics.js - Failed to load resource: net::ERR_NAME_NOT_RESOLVED
        # print(entry.source)# mostly network for requests or errors in javasript/html/css
        # print(entry.timestamp) # msec since epoch?
    return False


def take_screenshot_via_cdp_cmd(driver: WebDriver, width: int, height: Union[int, None] = None) -> bytes:
    """
    screenshot of the entire page with viewport selection
    when hieght is not specified the viewport will be extended 
    to fit the entire body of the page.
    """
    if height is None:
        layout = driver.execute_cdp_cmd("Page.getLayoutMetrics", {})
        height = layout["contentSize"]["height"]
    viewport = devtools.page.Viewport(0, 0, width, height, 1)
    img = driver.execute_cdp_cmd("Page.captureScreenshot", {
                                 "clip": viewport.to_json(), "captureBeyondViewport": True})
    return base64.b64decode(img['data'])


def _parse_css(url, _save_link, _save_failed_req, sess, parent_file, content, replace_links=False, _to_local_link=None):
    if type(content) == bytes:
        content = content.decode('utf-8')
    emtpy_parts = regex.findall(r"url\(\)", content)
    if len(emtpy_parts) != 0:
        logging.warning(
            "Warning: css seems to be malformed, empty url refs found, attemmting to clean it")
        content = content.replace(r"url\(\)", "")
    css_links = regex.findall(r'(?<=url\().+?(?=\))',
                              content)  # finds all "url(<link>)"
    css_links_set = set()
    for link in css_links:
        css_links_set.add(link)

    for link in css_links_set:
        if (not link.startswith('http') 
            and not link.startswith('"http') 
            and not link.startswith("'http") 
            and not link.startswith('"data:') 
            and not link.startswith('data:') 
            and not link.startswith("'data:")):
            logging.debug("Downloading resource: {}".format(link))
            #  calculate relative path by removing ../, then replace the original ref and remove " and '
            if link.startswith("\"") and link.endswith("\""):
                link = link.split("\"")[1]
            if link.startswith("\'") and link.endswith("\'"):
                link = link.split("\'")[1]
            "".startswith
            _parent_link = urljoin(url, parent_file)
            query_url = urljoin(_parent_link, link)
            if query_url.endswith(".mp4") or query_url.endswith(".webm") or query_url.endswith(".ogg"):
                continue
            try:
                _res = sess.get(query_url, timeout=31)
            except Exception as e:
                logging.exception("Failed to retive content for link {}".format(query_url))
                continue
            _content = _res.content
            if len(_content) > 2000000:
                logging.warning("Skiping ressource larger than 2MB: {}".format(query_url))
                continue
            realtive_link_parents = link.count("../") - (len(parent_file.split("/"))-1)
            relative_css_link = urljoin(parent_file, link)
            # more parents then expected -> prepend ../ to this path
            relative_css_link = "../"*realtive_link_parents + relative_css_link
            # remove trailing post params
            relative_css_link = relative_css_link.split("?", maxsplit=1)[0]  
            
               # css also support urls and links .. so we get to recurse
            if relative_css_link.endswith(".css") and parent_file != relative_css_link:
                _content = _parse_css(
                    url, _save_link, _save_failed_req, sess, relative_css_link, _content).encode()

            if _res.status_code < 400:
                _save_link(_content, relative_css_link)
                if replace_links:
                    local_link = _to_local_link(relative_css_link)
                    content = content.replace(relative_css_link, local_link)
            else:
                _save_failed_req(relative_css_link, query_url)
                logging.warning("resource {} not found, code: {}".format(
                    query_url, _res.status_code))

    return content


def download_page_raw(url: str, download_titel: str = "index", driver: WebDriver = None):
    """
    saves current page by parsing html and downloading found resources manually.
    returns None,status_code if driver is None and url was not found or leads to a redirct
    """
    page_content_links: Dict[str, Any] = dict()

    def _save_link(_content, _link):
        page_content_links.update({_to_local_link(_link): _content})

    failed_req: Dict[str, str] = dict()

    def _save_failed_req(_link, req_url):
        failed_req.update({_to_local_link(_link): req_url})

    def _to_local_link(_link: str):
        return download_titel + "_files/" + _link

    sess = requests.Session()
    sess.headers.update(EXTRA_HEADERS)
    main_page_from_requests = sess.get(url, timeout=31)
    if main_page_from_requests.status_code != 200:
        if driver is not None:
            page_source = driver.page_source
            page_source =  "<!DOCTYPE html>\n" + page_source
        else:
            return None, main_page_from_requests.status_code, None
    else:
        page_source = main_page_from_requests.content.decode()

    html = lxmlhtml.fromstring(page_source)
    converted_page = page_source
    ref_set = set()
    for ref_to_online_resource in html.xpath("head//@href") + html.xpath("//@src"):
        ref_set.add(str(ref_to_online_resource))
    for ref_to_online_resource in ref_set:
        if (not ref_to_online_resource.startswith('http') 
            and not ref_to_online_resource.startswith('"data:') 
            and not ref_to_online_resource.startswith('data:')):

            query_url = urljoin(base=url, url=ref_to_online_resource)
            try:
                res = sess.get(query_url, timeout=31)
            except Exception as e:
                logging.exception("Failed to retive content for link {}".format(query_url))
                continue
            ref = ref_to_online_resource.split("?", maxsplit=1)[0]  # remove trailing post params
            if res.status_code < 400:
                content = res.content
                if ref.endswith(".css"):  # css also support urls and links
                    content = _parse_css(
                        url, _save_link, _save_failed_req, sess, ref, content).encode()
                _save_link(content, ref)
            else:
                _save_failed_req(ref, query_url)
                logging.warning("resource {} not found, code: {}".format(
                    query_url, res.status_code))
            if ref.startswith("/"):
                converted_ref = "./" + \
                    _to_local_link(ref.split("/", maxsplit=1)[1])
            else:
                converted_ref = "./" + _to_local_link(ref)
            converted_page = converted_page.replace(
                "=\""+ref, "=\""+converted_ref)
            converted_page = converted_page.replace(
                "=\'"+ref, "=\'"+converted_ref)

    # for inline css code
    url = url.split("?", maxsplit=1)[0]
    if url.endswith("/"):
        parent_file = url.rsplit("/", maxsplit=1)[1]
    else:
        parent_file = url
    converted_page = _parse_css(
        url, _save_link, _save_failed_req, sess, parent_file, converted_page, True, _to_local_link)

    # TODO go through iframes recursivly
    """
    iframes = driver.findElements(By.tagName("iframe"))
    if len(iframes) != 0:
        super_context = driver.current_window_handle
        for frame in iframes:
            driver.switch_to(frame)
            save_page_via_selenium()
        #driver.switch_to(super_context)
        driver.switch_to.default_content()
    """
    return converted_page.encode(), page_content_links, failed_req


def save_page_via_gui_tabs(path: str, title: str = "index"):
    """
    Warning tabs are inconsistent the first time the application gest launched!.
    make sure chrome is in focus and not started in headless mode when using this function
    """
    pyautogui.hotkey("ctrl", "s")
    time.sleep(2)
    pyautogui.press("tab", 6, 0.2)
    time.sleep(1)
    pyautogui.press("space", 1)
    time.sleep(1)
    pyautogui.typewrite(path)
    time.sleep(1)
    pyautogui.hotkey("enter")
    time.sleep(3)
    pyautogui.press("tab", 7, 0.2)
    time.sleep(1)
    pyautogui.typewrite(title + ".html")
    time.sleep(1)
    pyautogui.hotkey("enter")
    time.sleep(5)
    pass


def save_page_via_gui_mouse(path: str, title: str = "index"):
    """
    This function assumes the "save as" window appears always
    at the SAME position in the the top left corner of the screen.
    Use with caution.
    """
    pyautogui.hotkey("ctrl", "s")
    time.sleep(1)
    pyautogui.typewrite(title+".html")
    time.sleep(1)
    pyautogui.moveTo(241, 87)
    time.sleep(1)
    pyautogui.click()
    time.sleep(1)
    pyautogui.typewrite(path)
    time.sleep(1)
    pyautogui.hotkey("enter")
    time.sleep(3)
    pyautogui.moveTo(1000, 903)
    time.sleep(1)
    pyautogui.click()
    pass




def get_css_from_element(driver: WebDriver, dom_el):
    """experimental"""
    ret = driver.execute_script(
        "return window.getComputedStyle(arguments[0],null).cssText", dom_el)
    pass

def get_style_of_element(element, driver):
    """Get all of the style properties for this element into a dictionary"""
    #https://stackoverflow.com/questions/32537339/getting-the-values-of-all-the-css-properties-of-a-selected-element-in-selenium
    return driver.execute_script('var items = {};'+
                                'var compsty = getComputedStyle(arguments[0]);'+
                                'var len = compsty.length;'+
                                'for (index = 0; index < len; index++)'+
                                '{items [compsty[index]] = compsty.getPropertyValue(compsty[index])};'+
                                'return items;', element)

def capture_elements(driver: WebDriver, url: str):
    if driver.current_url != url:
        driver.get(url)
        time.sleep(DELAY())
        wait_for_document_initialised(driver)

    captures =  {}
    def _screenshot_elements(**kwargs):
        time.sleep(DELAY())
        wait_for_document_initialised(driver)
        # try and capture some webelements, continue on fail
        try:
            elements = driver.find_elements(**kwargs)
            counter = 0
            for el in elements:
                try:
                    counter = counter + 1
                    html = el.get_attribute('outerHTML')
                    style = get_style_of_element(el, driver)
                    sh =  el.screenshot_as_png
                    captures.update({"{}_{}".format(kwargs["value"], counter):
                        {"css": style, "html": html, "screenshot": sh}})
                except Exception as e:
                    logging.exception("Error getting Webelement information")
                    pass
        except Exception as e:
            logging.exception("Could not locate elements with {}".format(kwargs))
            pass

    # img resizing

    # nparr = np.fromstring(extended_screenshot, np.uint8)
    # img_np = cv2.imdecode(nparr, cv2.CV_LOAD_IMAGE_COLOR)
    # img = cv2.imread('/home/img/python.png', cv2.IMREAD_UNCHANGED)    
    # scale_percent = 60 # percent of original size
    # width = int(img.shape[1] * scale_percent / 100)
    # height = int(img.shape[0] * scale_percent / 100)
    # dim = (width, height)
    # resized = cv2.resize(img, dim, interpolation = cv2.INTER_AREA)

    _screenshot_elements(by=By.TAG_NAME, value="header")
    _screenshot_elements(by=By.TAG_NAME, value="footer")
    _screenshot_elements(by=By.TAG_NAME, value="nav")
    _screenshot_elements(by=By.TAG_NAME, value="body")
    _screenshot_elements(by=By.TAG_NAME, value="main")
    _screenshot_elements(by=By.TAG_NAME, value="section")
    _screenshot_elements(by=By.TAG_NAME, value="article")
   
    return captures


def save_page_to_disc(driver: WebDriver, url, html, page_content, screenshots, path):
    return None


@contextlib.contextmanager
def setup_testenv() -> WebDriver:
    chrome_op = webdriver.ChromeOptions()
    chrome_op.add_extension('tools/I-don-t-care-about-cookies.crx')
    chrome_op.add_argument("--window-size={},{}".format(1920, 1080))
    # chrome_op.add_argument("--disable-web-security")
    # chrome_op.add_argument("--headless")
    with init_webdriver(path="tools/chromedriver.exe", op=chrome_op) as driver:
        yield driver


def test_save_as(url: str):
    with setup_testenv() as driver:
        driver.get(url)
        time.sleep(10)
        # wait_for_downloads(driver)
        #WebDriverWait(driver, 5).until(driver.execute_script("return 1"))
        # wait_for_document_initialised(driver,5)
        path = "C:\\git\\swipeproto\\temp\\"
        if not os.path.isdir(path):
            os.makedirs(path)
        # if check_if_window_present(driver):
        #    save_page_via_gui_mouse(path, title)
        return download_page_raw(driver=driver, url=url)


def test_browser_log():
    url = "https://www.zeit.de/news/2022-08/03/heckler-koch-erleidet-schlappe-vor-gericht"
    #url = "https://demo.frontted.com/flow/120220181311/index.html"
    test_save_as(url)
    with setup_testenv() as driver:
        driver.get("file://C:\\git\\swipeproto\\temp\\index.html")
        e = analyse_browser_logs_for_errors(driver)
    pass


def test_download():
    #test_page = "https://www.zeit.de/news/2022-08/03/heckler-koch-erleidet-schlappe-vor-gericht"
    #test_page = "http://max-themes.net/demos/grandresturant/demo1/home-2.html"
    #test_page = "https://demo.cocobasic.com/seppo-html/blog.html"
    #test_page = "https://template.hasthemes.com/uniqlo/uniqlo/index.html"
    #test_page = "http://html.creativegigs.net/charles/project.html"
    #test_page = "https://www.indonez.com/html-demo/Revusion/about.html"
    #test_page = "https://surielementor.com/monalhtml/blog-standard.html"
    #test_page = "https://solverwp.com/downloads/bizkar-creative-multi-purpose-react-template/?storefront=envato-elements" #react app
    test_page = "https://premiumlayers.com/html/infinity/?storefront=envato-elements"
    html, page_content, failed_req = test_save_as(test_page)
    with open(os.path.join("D:\\swipedata\\temp\\", "index.html"), "wb") as f:
        if type(html) != bytes:
            data = html.encode()
        else:
            data = html
        f.write(data)

    for key, val in page_content.items():
        os.makedirs(os.path.dirname(os.path.join(
            "D:\\swipedata\\temp\\", key)), exist_ok=True)
        with open(os.path.join("D:\\swipedata\\temp\\", key), "wb") as f:
            f.write(val)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_download()
    # test_browser_log()
    pass
