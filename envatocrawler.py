import logging
import os
import pickle
import time
import uuid
from functools import reduce
from typing import Any, Dict, Iterable, List, Union

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.webdriver import WebDriver
from models import Reference

import util

ENVATOELEMENTS_URL = "https://elements.envato.com/de/web-templates"
# css classes are based on the page code inspected at 16-5-2022 from Germany
def collect_store_links(driver) -> List:
    arr=[]
    templates_locator = driver.find_element(by=By.CLASS_NAME, value="tbCm4Hkx")
    link_elements = templates_locator.find_elements(By.TAG_NAME, 'li')
    for l in link_elements:
        arr.append(l.find_elements(by=By.CLASS_NAME, value="_MwuC0KD")[0].get_attribute("href"))
    return arr

def browse_store(driver:WebDriver) -> List[str]:
    x=1
    template_links = []
    b = False
    while True:
        driver.get(ENVATOELEMENTS_URL + "/pg-" + str(x))
        time.sleep(util.DELAY())
        util.wait_for_document_initialised(driver)
        headings = driver.find_element(by=By.TAG_NAME, value="h1")
        if isinstance(headings, list):
            for h in headings:
                string = h.get_attribute("innerHTML")
                if "404" in string:
                    b = True    
        else:
            string = headings.get_attribute("innerHTML")
            if "404" in string:
                b = True
        if b:
            break
        x=x+1
        template_links = template_links + collect_store_links(driver)
    return template_links

class EnvatoTemplate:
    """
    Holds meta data of e template from Envato.
    """
    tag_collection_css_class = "WzwRndT_"
    description_css_class = "RFDzdqtF"
    additions_collection_css_class = "oneAXbgM"
    titel_css_class = "D9ao138P"
    other_image_collection_css_class = "x0y_mRmw"
    main_image_outer_css_class = "MY02g2dt"
    demo_link_button_css_class = "x8uOcAS9"
    description_switch_button_css_class = "ywPnOlug"
    similar_templates_list_entries_css_class = "Ak8lAVqd"
    def __init__(self) -> None:
        self.store_url = ""
        self.store_title = ""
        self.tags = []
        self.description = ""
        self.description_original = ""
        self.additions = []
        self.titel = ""
        self.image = bytes()
        self.similar_templates = []
        self.demo_link = ""
        pass

    def __str__(self) -> str:
        #return "EnvatoTemplate" + self.uuid + "_" + self.titel + ", link: " + str(self.demo_link) +  ", tags: ["+ reduce( (lambda x,y: str(x)+ ", " + str(y)),self.tags) + "]"
        return "EnvatoTemplate" + str(self.uuid) + "_" + self.titel.replace(" ", "_")
        
def inspect_store_link(driver, link) -> EnvatoTemplate:
    driver.get(link)
    time.sleep(2)
    time.sleep(util.DELAY())
    util.wait_for_document_initialised(driver)

    envatoTemplate = EnvatoTemplate()
    envatoTemplate.store_url = link
    envatoTemplate.titel = driver.title

    titel_element = driver.find_element(by=By.CLASS_NAME, value=EnvatoTemplate.titel_css_class)
    envatoTemplate.titel = str(titel_element.get_attribute("innerHTML"))

    try:
        tags_outer = driver.find_element(by=By.CLASS_NAME, value=EnvatoTemplate.tag_collection_css_class)
        envatoTemplate.tags = [ str(a.get_attribute("innerHTML")) for a in tags_outer.find_elements(by=By.TAG_NAME, value="a") ]
    except:
        envatoTemplate.tags =  []
    try:
        description_outer = driver.find_element(by=By.CLASS_NAME, value=EnvatoTemplate.description_css_class)
        envatoTemplate.description = str(description_outer.get_attribute("innerHTML"))
    except:
        pass

    try:
        #description_switch = driver.find_element(by=By.CLASS_NAME, value=EnvatoTemplate.description_switch_button_css_class)
        #description_switch.click() # does not work for overlapping elements 
        driver.execute_script("""
        return document.getElementsByClassName(arguments[0])[0].click() 
        """, EnvatoTemplate.description_switch_button_css_class)
        envatoTemplate.description_original = str(description_outer.get_attribute("innerHTML"))
    except:
        pass
        
    try:
        button = driver.find_element(by=By.CLASS_NAME, value=EnvatoTemplate.demo_link_button_css_class)
        envatoTemplate.demo_link = str(button.find_element(by=By.TAG_NAME, value="a").get_attribute("href"))
    except:
        pass
    try: # sometimes this is missing 
        addtions_tags_outer = driver.find_element(by=By.CLASS_NAME, value=EnvatoTemplate.additions_collection_css_class)
        envatoTemplate.additions = [ str(a.get_attribute("innerHTML")) for a in addtions_tags_outer.find_elements(by=By.TAG_NAME, value="div") ]
    except:
        envatoTemplate.additions = []
    try:
        main_image_outer = driver.find_element(by=By.CLASS_NAME, value=EnvatoTemplate.main_image_outer_css_class)
        main_image_inner = main_image_outer.find_element(by=By.TAG_NAME, value="img")
        envatoTemplate.image = main_image_inner.screenshot_as_png
        #envatoTemplate.image.original = Image.download_from_url(envatoTemplate.image_main.url)
    except:
        envatoTemplate.image = None
    try:
        simliar_outer_list = driver.find_elements(by=By.CLASS_NAME, value=EnvatoTemplate.similar_templates_list_entries_css_class)
        for a in simliar_outer_list:
            envatoTemplate.similar_templates.append(str(a.find_element(by=By.TAG_NAME, value="a").get_attribute("href")))
    except:
        envatoTemplate.similar_templates = []

    return envatoTemplate

def collect_envato(driver: WebDriver) -> Iterable[EnvatoTemplate]:
    links = []
    pkl = "C:\\git\\swipeproto\\data\\template_links_pickle"
    if os.path.isfile(pkl):
        with open(pkl, "rb") as file:
            links = pickle.load(file)
    else:
        links = browse_store(driver)
        with open(pkl, "wb") as file:
            pickle.dump(links, file)
                
    for l in links:
        if  Reference.find_one({"store_url":l}) is None:
            yield inspect_store_link(driver, l)
        else:
            logging.info("url already in database, skipping url: {}".format(l))

