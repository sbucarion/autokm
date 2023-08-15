from PIL import Image
from pytesseract import pytesseract
import pyautogui
import os
import webbrowser
import pandas as pd
import cv2
import numpy as np
from pytesseract import Output
import imutils
import string 
from thefuzz import fuzz
from Levenshtein import distance, ratio
from numba import njit
import mss
from multiprocessing import Process
import threading
from datetime import datetime
import time
from thefuzz import fuzz
from screeninfo import get_monitors


def clean_word(word):
    for char in word:
        if char in string.punctuation:
            word = word.replace(char, "")
            
    for char in word:
        if not char.isalnum():
            word = word.replace(char, "")
            
    return word.strip().lower()


def clean_df(df):
    df['text'] = df['text'].apply(lambda x: clean_word(x))
    
    for i, row in df.iterrows():
        if row['text'] == "":
            df.at[i, 'text'] = np.nan
            
    df.dropna(inplace=True)
    df.reset_index(inplace=True)
    
    #pad dataframe for later use
    for _ in range(3):
        df = df._append(pd.Series("endofdataframe", index=df.columns), ignore_index=True)
        
    return df



@njit
def check_image_background(img):
    """Checks if a screenshots background is mainly white
        Will not invert if it is mainly white, changing a
        white photo to black will reduce performance because in
        docs it says algo performs best on white backgrounds"""
    score = 0
    PIXEL_MIN = 240
    SCORE_THRESHOLD = 0.7


    height, width, _ = img.shape
    
    for i in range(height):
        for j in range(width):
            if img[i, j][0] >= PIXEL_MIN and img[i, j][1] >=  PIXEL_MIN and img[i, j][2] >= PIXEL_MIN:
                score = score + 1
                
    if (score / (height*width)) < SCORE_THRESHOLD:
        return 1
    
    return 0


def preprocesser(file_path, opposite=False):
    """Allows for different preprocessing techniques to be added
    onto our input image to improve tesseract"""
    
    
    base_image = cv2.imread(file_path)
    
    #Current process inverts mainly black screenshots and coverts to grayscale
    #Same process for white but no inverting (try binarization for white)
    
    #Cant think of a better solution for the control flow of the opposite -> will think of one late
    if opposite is False:
        #For photos with mainly Black background
        if check_image_background(base_image):
            inverted_image = cv2.bitwise_not(base_image)
            gray_image = cv2.cvtColor(inverted_image, cv2.COLOR_BGR2GRAY)
            binarized_image = cv2.adaptiveThreshold(gray_image,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,11,2)

            return gray_image


        #For photos with mainly White background
        else:
            gray_image = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
            binarized_image_mean = cv2.adaptiveThreshold(gray_image,255,cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY,11,2) #Solid but not great
            binarized_image_gauss = cv2.adaptiveThreshold(gray_image,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,11,2) #Better

            #Both are actually good must test more and maybe adjust so the colors blue and orange get changed wht & nt blk

            return gray_image
        
        
    else:
        if not check_image_background(base_image):
            inverted_image = cv2.bitwise_not(base_image)
            gray_image = cv2.cvtColor(inverted_image, cv2.COLOR_BGR2GRAY)
            binarized_image = cv2.adaptiveThreshold(gray_image,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,11,2)

            return gray_image

        else:
            gray_image = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
            binarized_image_mean = cv2.adaptiveThreshold(gray_image,255,cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY,11,2) #Solid but not great
            binarized_image_gauss = cv2.adaptiveThreshold(gray_image,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,11,2) #Better
            
            return gray_image
        
        
#New program works up to this point

        
#Multithread the process to speed up the image extraction        
def process_image(file_path, df_list, monitor_number, alternative=False, show_image=True):
    psm_version = "--psm 11"
    
    preprocessed_image = preprocesser(file_path, alternative)
    
    image_df = pd.DataFrame(pytesseract.image_to_data(preprocessed_image, output_type=Output.DICT, config=psm_version))
    
    time.sleep(0.1)

    image_df = clean_df(image_df)
    
    df_list.append((image_df, monitor_number)) #Add to a list because idk how to return when multithreading
    
    if show_image is True:
        image_df = image_df[:-3]
        
        n_boxes = len(image_df['level'])
        for i in range(n_boxes):
            (x, y, w, h) = (int(image_df['left'][i]), int(image_df['top'][i]), int(image_df['width'][i]), int(image_df['height'][i]))
            cv2.rectangle(preprocessed_image, (x, y), (x + w, y + h), (0,0,0), 2)

        cv2.imshow('img', preprocessed_image)
        cv2.waitKey(0)
        
    return

    
#Pretty sure it works up to here
def get_moitor_number(montior_string):
    for char in montior_string:
        if char.isdigit():
            return char



def multithread_image_processing(folder_path, dfs):
    image_paths = get_images_paths(folder_path)
    
    for path in image_paths:
        monitor_path = folder_path + "\\" + path 
        monitor_number = get_moitor_number(path)
        
        threading.Thread(target=process_image, args=(monitor_path, dfs, monitor_number, False,)).start()
        threading.Thread(target=process_image, args=(monitor_path, dfs, monitor_number, True,)).start()
        
    return

#start refactoring here


#Now extract lines or words from the dataframes
def extract_text_lines(image_df):
    df = image_df.iloc[:-3]
    df = df[df.conf != -1]

    df["conf"] = pd.to_numeric(df["conf"], downcast="float")

    #Apply only works for single columns
    for column in ["left", "top", "height", "width"]:
        df[column] = pd.to_numeric(df[column], downcast="float")
    
    
    lines = df.groupby(['page_num', 'block_num', 'par_num', 'line_num'])['text'].apply(lambda x: ' '.join(list(x))).tolist()
    #Ifuckging hate pandas so much its never wants to let you do things easily
    
    left_coors = df.groupby(['page_num', 'block_num', 'par_num', 'line_num'])['left'].mean().round().tolist()
    top_coors = df.groupby(['page_num', 'block_num', 'par_num', 'line_num'])['top'].mean().round().tolist()
    height_coors = df.groupby(['page_num', 'block_num', 'par_num', 'line_num'])['height'].mean().round().tolist()
    width_coors = df.groupby(['page_num', 'block_num', 'par_num', 'line_num'])['width'].mean().round().tolist()
    
    confs = df.groupby(['page_num', 'block_num', 'par_num', 'line_num'])['conf'].mean().tolist()

    
    tuple_results = list(zip(lines, left_coors, top_coors, height_coors, width_coors))
    
    results = []
    for row in tuple_results:
        results.append([row[0], tuple(row[1:])])
        
    return results


def locate_text(df, text):
    results = []

    stripped_text = "".join(text.lower().split())
    split_text = text.split()
    
    for i, row in df.iterrows():
        word = row['text'].lower()

        second_word = df.iloc[i+1]['text'].lower()

        initial_fuzz = fuzz.ratio(word, stripped_text)
        second_fuzz = fuzz.ratio((word+second_word), stripped_text)
        
        if word == "endofdataframe":
            break
            
        if initial_fuzz >= 80:
            if initial_fuzz < second_fuzz:
                results.append([(word+second_word), (row["left"], row["top"], row["height"], row["width"]),second_fuzz])
                
            else:
                results.append([word, (row["left"], row["top"], row["height"], row["width"]), initial_fuzz])


        if second_fuzz >= 80 and initial_fuzz < 80:
            results.append([(word+second_word), (row["left"], row["top"], row["height"], row["width"]),second_fuzz])
                
                
        else:
            if word in split_text[0] or split_text[0] in word: #may need to do partial_ratio(split_text[0], word)
                word = word
                second_word = word + df.iloc[i+1]['text'].lower()
                
                r1 = fuzz.ratio(word, stripped_text)
                r2 = fuzz.ratio(second_word, stripped_text)
                
                j = i + 2 #sets j to current word in df
                count = 0
                
                while r2 >= r1:
                    word = second_word
                    second_word = word + df.iloc[j]['text'].lower()
                    
                    r1 = fuzz.ratio(word, stripped_text)
                    r2 = fuzz.ratio(second_word, stripped_text)
                    
                    if r2 >= 80:
                        results.append([second_word, (row["left"], row["top"], row["height"], row["width"]), r2])
                    
                    word = second_word
                
                    count += 1
                    j+=1
                
    return results


def find_best_phrases(phrase_data, text):
    results = []
    
    for i, row in enumerate(phrase_data):
        r = fuzz.ratio(row[0], text)
        phrase_data[i].append(r)
        
    for row in phrase_data:
        if row[-1] >= 70:
            results.append(row)
            
    return results


def get_images_paths(folder_path):
    image_paths = []
    for file in os.listdir(folder_path):
        if ".png" in file:
            image_paths.append(file)
        
    return image_paths


def process_textual_data(data):
    """Find the best match to target and return coors"""
    tmp_res = []
    max_fuzz = 0
    max_coors = 0
    monitor_loc = 1
    
    for item in data:
        monitor_num = item[-1]
        item_max_fuzz = 0
        item_max_coors = 0
        
        for match in item:
            if isinstance(match,str):
                continue
            
            if match[-1] > item_max_fuzz:
                item_max_fuzz = match[-1]
                item_max_coors = match[-2]
                
        if item_max_fuzz > max_fuzz:
            max_fuzz = item_max_fuzz
            max_coors = item_max_coors
            monitor_loc = monitor_num
        
    return process_coordinates(max_coors, monitor_loc)



def process_coordinates(coors, monitor_num):
    x = coors[0] + (coors[-1] // 1.5)
    y = coors[1] + (coors[-2] // 1.5)
    
    #Check if monitor two and adjust coors
    if monitor_num == "2":
        monitor_data = get_monitors()[1]
        
        x += monitor_data.x + x
        
    return x, y
        

def get_coordinates(target, folder_path):
    """Given text and screenshot path function will find location
        of text on the screenshot and return the pixel coordinates"""
    
    #Setup PyTesseract
    current_dir = os.getcwd()
    path_to_tesseract = r"C:\Users\sbuca\Documents\pierre\autokm\Tesseract-OCR\tesseract.exe" #will fail in jupyter folder

    pytesseract.tesseract_cmd = path_to_tesseract
    
    target = target.lower()

    #Extract Raw Data From The Screen
    dfs = []
    multithread_image_processing(folder_path, dfs) 
    
    
    #Dynamic wait to let all threads finish
    while len(dfs) < (len(get_images_paths(folder_path))*2):
        time.sleep(0.05)
    

    #Finds all instances of our target (coors and monitor too)
    data = []
    for df, monitor_num in dfs:
        phrase_data = extract_text_lines(df)
        text_data = locate_text(df, target)

        #Get coor and fuzz data for the lines method
        best_phrases = find_best_phrases(phrase_data, target)

        results = best_phrases + text_data

        if results != []:
            results.append(monitor_num)
            data.append(results)
            
            
    coors = process_textual_data(data)
    return coors


if __name__ == "__main__":
    get_coordinates(target, folder_path)
    process_image(file_path, df_list, alternative=False, show_image=False)