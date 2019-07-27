
# imports
from time import sleep, strftime
import datetime
import time
import numpy as np
import scipy.interpolate as si
import re
import os
import pandas as pd

# webscraper imports
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains


def rand_sleep(length=None):
    if (length is None) or (length == "short"):
        tm = np.random.randint(2,10)
    elif length == "long":
        tm = np.random.randint(20,60)
    elif length == "minutes":
        tm = np.random.randint(90,60*5)
    elif length == "1hour":
        tm = np.random.randint(60*60,60*90)
    else:
        tm = 5
    
    print("...sleeping for %isec" % tm)
    sleep(tm)
    return


def set_up():
    '''
    open browser
    set preferences to ignore 'notification' dialog from chrome
    '''
    #chromedriver_path='C:/Users/roddt/Desktop/flights/chromedriver/download/chromedriver.exe'
    chromedriver_path='chromedriver/download/chromedriver.exe'

    chrome_options = webdriver.ChromeOptions()
    prefs = {"profile.default_content_setting_values.notifications" : 2}
    chrome_options.add_experimental_option("prefs",prefs)

    driver = webdriver.Chrome(executable_path=chromedriver_path, options=chrome_options)
    #action =  ActionChains(driver)
    
    print("initial page opened")
    rand_sleep()
    
    return driver


def go_home():
    '''
    no go to reddit as a starting point
    i thought this would mimic following a link from reddit...shrug emoji
    '''
    reddit = "https://www.reddit.com/r/travel/new"
    driver.get(reddit)
    print("made to to reddit")
    rand_sleep()

    comments = '//a[@data-click-id = "comments"]'
    driver.find_element_by_xpath(comments).click()
    print("made it to comments")
    rand_sleep()
    
    return


def catch_popup():
    '''
    this is pretty much straight from the article and the dude's code...only works on a particular popup
    '''
    try:
        xp_popup_close = '//button[contains(@id,"dialog-close") and contains(@class,"Button-No-Standard-Style close ")]'
        driver.find_elements_by_xpath(xp_popup_close)[5].click()
        print("caught pop up")
        rand_sleep()
    except Exception as e:
        print("no pop up")
        pass
    return


def get_to_url(url, debug=False):
    '''
    goes to url and tries to look for a redirect to a captcha page
    ...haven't figured out a fool proof way to avoid tbh
    '''
    driver.get(url)
    
    # check for captcha
    xp_results_table = '//*[@id = "px-captcha"]'
    captcha = driver.find_elements_by_xpath(xp_results_table)
    if captcha:
        print("CAPTCHA PAGE - %s" % (datetime.datetime.now().time()))
        if debug:
            print("DEBUG ON...exiting")
            return
        go_home()
        rand_sleep("1hour")
        # try again
        driver.get(url)
        captcha = driver.find_elements_by_xpath(xp_results_table)
        if captcha:
            print("failed to evade captcha...EXIT")
            return "FAILED"
        else:
            print("successfully evaded captcha!")
    print("got to url")
    rand_sleep("long")
    return


def parse_text(flight_element, home, dest):
    '''
    we can split by \n for flight_element but the len() of the output is variable
    also we need to separate the data from one leg to the other
    then there can also be more than one amount so pick the $ before "View Deal"
    '''
    starts = []
    for match in re.finditer("\d{1,2}/\d{1,2}", flight_element):
        starts.append(match.start())
    ends = []
    ends.append(re.search("%s.*%s" % (home, dest), flight_element).end())
    ends.append(re.search("%s.*%s" % (dest, home), flight_element).end())
    # get the flight info for each leg
    data = {}
    for s,e,cat in zip(starts,ends,['Depart','Return']):
        info = flight_element[s:e].split("\n")
        mm, dd = info[0].split("/") # mm/dd
        yr = datetime.datetime.now().year
        if datetime.datetime.now().month > int(mm):
            # handle the Dec -> Jan transition
            yr += 1
        # takeoff time
        start_tm = info[2].split(" ")[0] + info[2].split(" ")[1]
        tkoff = "%i-%s-%s %s" % (yr, mm, dd, start_tm)
        tkoff_obj = datetime.datetime.strptime(tkoff,'%Y-%m-%d %I:%M%p')
        # landing time
        end_tm = info[2].split(" ")[3] + info[2].split(" ")[4]
        lnd = "%i-%s-%s %s" % (yr, mm, dd, end_tm)
        lnd_obj = datetime.datetime.strptime(lnd,'%Y-%m-%d %I:%M%p')
        if info[2].split(" ")[-1] == "+1":
            # then add a day to return date
            lnd_obj = lnd_obj + datetime.timedelta(days=1)
        data['%s Takeoff DateTimeObj' % cat] = tkoff_obj
        data['%s Landing DateTimeObj' % cat] = lnd_obj
        data['%s DateTimeStr' % cat] = "%s %s @ %s " % (info[1],info[0],info[2])
        # now handle duration
        hh,mm = info[6].split(" ")
        dur_obj = datetime.timedelta(hours=int(hh[:-1]), minutes=int(mm[:-1]))
        data['%s Duration TimeDelta' % cat] = dur_obj
        data['%s Duration Str' % cat] = "%s w/ %s" % (info[6],info[4])
    # get price
    # grab the first $
    ammount = re.search("\$\d*", flight_element).group()
    data['Price'] = int(ammount[1:])
    #data['Carrier'] = flight_element[e+1:].split("\n")[0] #not right
    data['tag'] = ""
    if "Sponsor" in flight_element:
        data['tag'] = "Sponsored"
    if "Best" in flight_element:
        data['tag'] = "Best"
    if "Cheapest" in flight_element:
        data['tag'] = "Cheapest"
    return data


def scrape_page(home, destination):
    '''
    now actually go and grab the info from the page
    '''
    catch_popup()
    
    xp_results_table = '//*[@class = "resultWrapper"]'
    flight_containers = driver.find_elements_by_xpath(xp_results_table)
    flights_list = [flight.text for flight in flight_containers]
    
    data_list = []
    for flight_element in flights_list:
        data_dict = parse_text(flight_element, home, destination)
        data_list.append(data_dict)
    
    print("finished url scraping")
    return data_list


def build_kayak_link(home="ATL", destination=None,
                     depart_date=None, return_date=None,
                     depart_dow=None, return_dow=None, num_weeks=None, buffer=2,
                     flexible=None,
                     sort=None):
    '''
    trying to mimic this...
    https://www.kayak.com/flights/ATL-BFS/2019-09-06-flexible-1day/2019-09-09-flexible-1day?sort=price_a
    
    * the dates can be explicit yyyy-mm-dd
    * could also give day of the week and will search that day of the week for the next #ofweeks
    * I JUST REALIZED THAT THIS ONLY WORKS IF YOUR DEPART DOW IS TOWARDS END OF THE WEEK AND RETURN IS EARLY
    * flexible needs to be an int [1,2,3]
    * sort needs to be ["price","best","time"]
    '''
    if (depart_date is not None) and (return_date is not None):
        departs = [depart_date]
        returns = [return_date]
    elif (depart_dow is not None) and (return_dow is not None) and (type(num_weeks) is int):
        dow = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        assert ((depart_dow in dow) and (return_dow in dow)), "wrong dow; make sure to capitalize"
        # get dow in a format that datetime object will understand
        today = datetime.datetime.today()
        depart_dow = int(np.argwhere(depart_dow==np.array(dow))[0,0]) # super ugly, sorry
        return_dow = int(np.argwhere(return_dow==np.array(dow))[0,0])
        if depart_dow < return_dow:
            trip_days = return_dow - depart_dow
        elif depart_dow > return_dow:
            trip_days = (7-depart_dow) + return_dow
        else:
            trip_days = 7
        if today.weekday() <= depart_dow:
            index_date = today + datetime.timedelta(weeks=2, days=depart_dow-today.weekday())
        else: #today.weekday() > depart_dow
            index_date = today + datetime.timedelta(weeks=2, days=7-today.weekday()+depart_dow)
        departs = []
        returns = []
        for w in range(num_weeks):
            depart_datetime = index_date + datetime.timedelta(weeks=w)
            departs.append(depart_datetime.strftime('%Y-%m-%d'))
            returns.append((depart_datetime+datetime.timedelta(days=trip_days)).strftime('%Y-%m-%d'))
    else:
        print("User Error: gave incomplete date information")
        return 0
    
    assert ((type(home) is str) and (type(destination) is str)), "invalid value for home/destination"
    assert ((sort is None) or (sort in ["price", "best", "time"]))
    sort_valid_values = {
        None : "bestflight_a",
        "price" : "price_a",
        "best" :  "bestflight_a",
        "time" : "duration_a"
    }
    
    urls = []
    for dep, ret in zip(departs, returns):
        if flexible is None:
            url = "https://www.kayak.com/flights/%s-%s/%s/%s?sort=%s" % (
                        home, destination,
                        dep, ret,
                        sort_valid_values[sort])
        else:
            assert (flexible in [1,2,3]), "invalid value for 'flexible'"
            url = "https://www.kayak.com/flights/%s-%s/%s-flexible-%iday/%s-flexible-%iday?sort=%s" % (
                        home, destination, 
                        dep, flexible,
                        ret, flexible,
                        sort_valid_values[sort])
        urls.append(url)
    
    return urls


def move_mouse(plot=False):
    '''
    https://stackoverflow.com/questions/39422453/human-like-mouse-movements-via-selenium
    https://github.com/guilhermebferreira/selenium-notebooks/blob/master/Mouse%20move%20by%20b-spline%20interpolation.ipynb
    '''
    start_time = time.time()
    
    # set up curve
    start = np.random.randint(-10,10+1,2) # STARTING LOCATION
    my_points = [start]
    length = np.random.randint(40,80) # NUMBER OF MOVEMENTS
    for i in range(length//5):
        new = my_points[-1] + np.random.randint(-200,200+1,2) # STEP SIZES
        my_points.append(new)
    my_points = np.array(my_points)
    x = my_points[:,0]
    y = my_points[:,1]
    t = range(len(my_points))
    ipl_t = np.linspace(0.0, len(my_points) - 1, length) # FINAL NUMBER OF MOVEMENTS
    x_tup = si.splrep(t, x, k=3)
    y_tup = si.splrep(t, y, k=3)
    x_list = list(x_tup)
    xl = x.tolist()
    x_list[1] = xl + [0.0, 0.0, 0.0, 0.0]
    y_list = list(y_tup)
    yl = y.tolist()
    y_list[1] = yl + [0.0, 0.0, 0.0, 0.0]
    x_i = si.splev(ipl_t, x_list)
    y_i = si.splev(ipl_t, y_list)
    if plot:
        import matplotlib.pyplot as plt
        plt.scatter(start[0],start[1])
        plt.plot(x_i,y_i)

    #decide starting location
    coin_flip = np.random.choice(["by_code","by_dealbutton"])
    if coin_flip == "by_code":
        code = np.random.choice(['price','bestflight','duration'])
        xpath = '//a[@data-code = "%s"]' % code
        startElement = driver.find_element_by_xpath(xpath)
    elif coin_flip == "by_dealbutton":
        xpath = '//*[@class = "booking-link"]'
        startElement = np.random.choice(driver.find_elements_by_xpath(xpath))
    else:
        print("whut, how?")
    action =  ActionChains(driver)
    action.move_to_element(startElement)
    try:
        action.perform()
    except:
        print("failed to get to starting location")
        print("...%s - %s" % (coin_flip, startElement.text))
        sleep(5)
    
    # perform mouse movement
    for m, (mouse_x, mouse_y) in enumerate(zip(x_i,y_i)):
        if (plot) and (m%10==0): print(m)
        try:
            action.move_by_offset(mouse_x,mouse_y)
            action.perform()
        except Exception as e:
            #print(mouse_x,mouse_y, e)
            pass
        sleep(np.random.random()*.1)
    
    print("mouse movements - %.2fsec" % (time.time()-start_time))
    return


def click_filter(attempt=0):
    start_time = time.time()
    
    if attempt == 3:
        print("refreshing page")
        driver.refresh()
        rand_sleep("long")
        catch_popup()
    elif attempt >= 6:
        print("giving up, can't fix this")
        exit()
    
    xp_results_table = '//*[@class = "filterSectionTitle"]'
    flight_containers = driver.find_elements_by_xpath(xp_results_table)
    action =  ActionChains(driver)
    i = np.random.randint(0,len(flight_containers))
    try:    
        action.move_to_element(flight_containers[i])
        flight_containers[i].click()
        print("successfully clicked around")
    except:
        print("clicking failed - trying again")
        attempt += 1
        click_filter(attempt)
        return
        
    sleep(np.random.random()*5)
    print("random clicking - %.2fsec" % (time.time()-start_time))
    return


def write_data(data_list, home, destination):
    csv = "data/%s_%s.csv" % (home,destination)
    if os.path.exists(csv):
        write_mode = "a"
        write_header = False
    else:
        write_mode = "w"
        write_header = True

    df = pd.DataFrame(data_list)
    df['Parsed Date'] = datetime.datetime.now()
    df.to_csv(csv, header=write_header, index=False, mode=write_mode)
    print("successfully wrote data to file")
    
    return csv


####################################################################################################
if __name__ == "__main__":
    home = "ATL"

    driver = set_up()
    for destination in ["EDI","MAD","SFO"]:
        data_list = []
        urls= build_kayak_link(home="ATL", destination=destination,
                               depart_date=None, return_date=None,
                               depart_dow="Friday", return_dow="Monday", num_weeks=9, buffer=3,
                               flexible=1,
                               sort="best")
        go_home()
        print("STARTING NEW DESTINATION - %s - %s" % (destination, datetime.datetime.now().time()))
        for url in urls:
            status = get_to_url(url, debug=False)
            if status == "FAILED":
                break
            catch_popup()
            rand_sleep("long")
            click_filter()
            move_mouse()
            # SCRAPE DATA
            data_list += scrape_page(home, destination)
            for code in ["price","duration"]: # should have started with bestflight
                xpath = '//a[@data-code = "%s"]' % code
                driver.find_element_by_xpath(xpath).click()
                # SCRAPE DATA
                #data_list += scrape_page(home, destination)
                move_mouse()
            #rand_sleep("minutes")
            coin_flip = np.random.random()
            if coin_flip <= 0.0:
                go_home()
            else:
                move_mouse()
                #rand_sleep("minutes")
                pass
            
        csv = write_data(data_list, home, destination)
        plot_data(csv)