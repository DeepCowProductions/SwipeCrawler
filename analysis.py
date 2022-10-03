from dataclasses import dataclass
import cv2


def compute_color_histogram(img:bytes):
    pass

def compute_greyscale_histogram(img:bytes):
    pass

def compute_contrast(img:bytes):
    pass

def compute_brightness(img:bytes):
    pass

def compute_color_temperature(img:bytes):
    pass


@dataclass
class FontUsage:
    name:str = ""
    apearance_percent:int = 0 

"""
a font apears x times with individual sizes y (x*y)
a use has a position in the html and some size, text length/ chars used
it can be bold cursive crossed and underscored
it can appear in certain html tags like: div h1 h2 or span button a

style can also be in relation to common webelements like navbars sitebars buttons headings links etc
and print out information regarding the font/size/style/color that theese elements typicly apear in
"""

def compute_text_style(html:str, css:str):
    pass

def compute_design_style(html:str, css:str):
    """flat <-> material"""
    #TODO not sure how 
    # maybe look for border curves and shadows, maybe use some ml or cv
    pass

def compute_information_density():
    #TODO not sure how yet
    pass
