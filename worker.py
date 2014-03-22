#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2014, YongSeok Choi <sseeookk@gmail.com> based on the Goodreads work by Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

import socket, re, datetime, lxml
from collections import OrderedDict
from threading import Thread

from lxml.html import fromstring, tostring

from calibre.ebooks.metadata.book.base import Metadata
from calibre.library.comments import sanitize_comments_html
from calibre.utils.cleantext import clean_ascii_chars
from calibre.utils.localization import canonicalize_lang

import calibre_plugins.kyobobook.config as cfg

class Worker(Thread): # Get details

    '''
    Get book details from Kyobobook book page in a separate thread
    '''

    def __init__(self, url, result_queue, browser, log, relevance, plugin, timeout=20):
        Thread.__init__(self)
        self.daemon = True
        self.url, self.result_queue = url, result_queue
        self.log, self.timeout = log, timeout
        self.relevance, self.plugin = relevance, plugin
        self.browser = browser.clone_browser()
        self.cover_url = self.kyobobook_id = self.isbn = None

        lm = {
                'eng': ('English', 'Englisch','ENG'),
                'zho': ('Chinese', 'chinois','chi'),
                'fra': ('French', 'Francais','FRA'),
                'ita': ('Italian', 'Italiano','ITA'),
                'dut': ('Dutch','DUT',),
                'deu': ('German', 'Deutsch','GER'),
                'spa': ('Spanish', 'Espa\xf1ol', 'Espaniol','SPA'),
                'jpn': ('Japanese', u'日本語','JAP'),
                'por': ('Portuguese', 'Portugues','POR'),
                'kor': ('Korean', u'한국어','KOR'),
                }
        self.lang_map = {}
        for code, names in lm.iteritems():
            for name in names:
                self.lang_map[name] = code

    def run(self):
        try:
            self.get_details()
        except:
            self.log.exception('get_details failed for url: %r'%self.url)

    def get_details(self):
        try:
            raw = self.browser.open_novisit(self.url, timeout=self.timeout).read().strip()
        except Exception as e:
            if callable(getattr(e, 'getcode', None)) and \
                    e.getcode() == 404:
                self.log.error('URL malformed: %r'%self.url)
                return
            attr = getattr(e, 'args', [None])
            attr = attr if attr else [None]
            if isinstance(attr[0], socket.timeout):
                msg = 'Kyobobook timed out. Try again later.'
                self.log.error(msg)
            else:
                msg = 'Failed to make details query: %r'%self.url
                self.log.exception(msg)
            return

        # open('c:\\Kyobobook1.html', 'wb').write(raw)
        # raw = raw.decode('utf-8', errors='replace') #00
        # open('c:\\Kyobobook2.html', 'wb').write(raw)

        # if '<title>404 - ' in raw:
            # self.log.error('URL malformed: %r'%self.url)
            # return

        try:
            root = fromstring(clean_ascii_chars(raw))
        except:
            msg = 'Failed to parse Kyobobook details page: %r'%self.url
            self.log.exception(msg)
            return

        try:
            # Look at the <title> attribute for page to make sure that we were actually returned
            # a details page for a book. If the user had specified an invalid ISBN, then the results
            # page will just do a textual search.
            title_node = root.xpath('//title')
            if title_node:
                page_title = title_node[0].text_content().strip()
                
                # search success : "나의 문화유산답사기 1 - 인터넷교보문고"
                # search fail : " - 인터넷교보문고"
                if page_title is None or page_title == " - 인터넷교보문고":
                    self.log.error('Failed to see search results in page title: %r'%self.url)
                    return
        except:
            msg = 'Failed to read Kyobobook page title: %r'%self.url
            self.log.exception(msg)
            return

        errmsg = root.xpath('//*[@id="errorMessage"]')
        if errmsg:
            msg = 'Failed to parse Kyobobook details page: %r'%self.url
            msg += tostring(errmsg, method='text', encoding=unicode).strip()
            self.log.error(msg)
            return

        self.parse_details(root)

    def parse_details(self, root):
        try:
            kyobobook_id = self.parse_kyobobook_id(self.url)
        except:
            self.log.exception('Error parsing Kyobobook id for url: %r'%self.url)
            kyobobook_id = None
        
        try:
            (title, series, series_index) = self.parse_title_series(root)
        except:
            self.log.exception('Error parsing title and series for url: %r'%self.url)
            title = series = series_index = None

        try:
            authors = self.parse_authors(root)
        except:
            self.log.exception('Error parsing authors for url: %r'%self.url)
            authors = []

        if not title or not authors or not kyobobook_id:
            self.log.error('Could not find title/authors/kyobobook id for %r'%self.url)
            self.log.error('Kyobobook: %r Title: %r Authors: %r'%(kyobobook_id, title,
                authors))
            return

        mi = Metadata(title, authors)
        if series:
            mi.series = series
            mi.series_index = series_index
        mi.set_identifier('kyobobook', kyobobook_id)
        self.kyobobook_id = kyobobook_id

        try:
            isbn = self.parse_isbn(root)
            if isbn:
                self.isbn = mi.isbn = isbn
        except:
            self.log.exception('Error parsing ISBN for url: %r'%self.url)

        try:
            mi.rating = self.parse_rating(root)
        except:
            self.log.exception('Error parsing ratings for url: %r'%self.url)

        try:
            mi.comments = self.parse_comments(root)
        except:
            self.log.exception('Error parsing comments for url: %r'%self.url)

        try:
            self.cover_url = self.parse_cover(root)
        except:
            self.log.exception('Error parsing cover for url: %r'%self.url)
        mi.has_cover = bool(self.cover_url)

        try:
            tags = self.parse_tags(root)
            if tags:
                mi.tags = tags
        except:
            self.log.exception('Error parsing tags for url: %r'%self.url)

        try:
            mi.publisher, mi.pubdate = self.parse_publisher_and_date(root)
        except:
            self.log.exception('Error parsing publisher and date for url: %r'%self.url)

        try:
            lang = self._parse_language(root)
            if lang:
                mi.language = lang
        except:
            self.log.exception('Error parsing language for url: %r'%self.url)

        mi.source_relevance = self.relevance

        if self.kyobobook_id:
            if self.isbn:
                self.plugin.cache_isbn_to_identifier(self.isbn, self.kyobobook_id)
            if self.cover_url:
                self.plugin.cache_identifier_to_cover_url(self.kyobobook_id,
                        self.cover_url)

        self.plugin.clean_downloaded_metadata(mi)

        self.result_queue.put(mi)

    def parse_kyobobook_id(self, url):
        # return re.search('&barcode=([^\&]+)', url).groups(0)[0]
        return re.search('[\?|\&]barcode=([^\&]+)', url).group(1)

    def parse_title_series(self, root):
        title_node = root.xpath('//div[@class="title_icon"]/h1[@class="title"]')
        if not title_node:
            return (None, None, None)
        self._removeTags(title_node[0],["script","style"])
        
        title_text = title_node[0].text_content().strip() 
        
        series_node = root.xpath('//div[@class="title_icon"]/div[@class="info"]')
        if not series_node:
            return (title_text, None, None)
        series_info = series_node[0].text_content()
        
        series_name = None
        series_index = None
        if series_info:
            try:
                series = series_info.split("|")
                if len(series) > 1:
                    series_name = series[0].strip()
                    series_index = float(series[1].strip())
            except:
                series_name = None
                series_index = None
                
        return (title_text, series_name, series_index)


    def parse_authors(self, root):
        # Build a dict of authors with their contribution if any in values
        authors_elements = root.xpath("//span[@title='%s']/preceding-sibling::node()" % u'출판사')

        if not authors_elements:
            return

        authors_type_map = OrderedDict()
        #authors_elements_len = len(authors_elements)
        authors_elements.reverse()
        
        # 거꾸로 검색하면서 "역할"을 할당한다.
        contrib = ''
        for el in authors_elements:
            # print div_authors[n-1]
            #el = authors_elements[n-1]
            self._removeTags(el,["div","script","style"])
            if isinstance(el, lxml.html.HtmlElement) and contrib:
                if el.get("class") != "name": continue
                spliter = ","
                if re.search("detailViewEng",self.url): spliter = "/"
                authors_splits = re.sub("\s{2,}"," ",el.text_content().strip()).replace("／","/").split(spliter)
                authors_splits.reverse()
                for authors_split in authors_splits:
                    if '(' in authors_split:
                        #log.info('Stripping off series(')
                        authors_split = authors_split.rpartition('(')[0]
                    authors_split = re.sub("(\s외|\s편|著 |\[著\]|編 )","",authors_split).strip()
                    if authors_split in authors_type_map.keys(): del authors_type_map[authors_split]
                    authors_type_map[authors_split] = contrib
            elif isinstance(el, lxml.etree._ElementUnicodeResult):
                if el.strip():
                    contrib = el.strip()
        item = authors_type_map.items()
        item.reverse()
        authors_type_map = OrderedDict(item)

        # User either requests all authors, or only the primary authors (latter is the default)
        # If only primary authors, only bring them in if:
        # 1. They have no author type specified
        # 2. They have an author type of 'Kyobobook Author'
        # 3. There are no authors from 1&2 and they have an author type of 'Editor'
        get_all_authors = cfg.plugin_prefs[cfg.STORE_NAME][cfg.KEY_GET_ALL_AUTHORS]
        authors = []
        valid_contrib = None
        for a, contrib in authors_type_map.iteritems():
            if get_all_authors:
                authors.append(a)
            else:
                if not contrib or contrib == u'지음' or contrib == u'저자':
                    authors.append(a)
                elif len(authors) == 0:
                    authors.append(a)
                    valid_contrib = contrib
                elif contrib == valid_contrib:
                    authors.append(a)
                else:
                    break
        return authors

    def parse_rating(self, root):
        rating_node = root.xpath('//a[@href="#review"]/img')
        if rating_node:
            rating_text = rating_node[0].get("alt")
            rating_num = re.search(u"5점 만점에 (\d)점",rating_text).group(1)
            if rating_num:
                rating_value = int(rating_num)
                return rating_value

    def parse_comments(self, root):
        description_node = root.xpath('//dl[@class="book_info_detail"]/dd[@class="content"]')
        
        default_append_toc = cfg.DEFAULT_STORE_VALUES[cfg.KEY_APPEND_TOC]
        append_toc = cfg.plugin_prefs[cfg.STORE_NAME].get(cfg.KEY_APPEND_TOC, default_append_toc)
        
        comments = ''
        if description_node:
            comments += tostring(description_node[0], method='html', encoding=unicode).strip()
            while comments.find('  ') >= 0:
                comments = comments.replace('  ',' ')
            comments = sanitize_comments_html(comments)
            
        if append_toc:
            toc_node = root.xpath('//div[@class="book_info"]/h2[@class="book_d_title" and contains(text(),"%s")]/following-sibling::div' % u"목차")
            if toc_node:
                toc = tostring(toc_node[0], method='html')
                toc = sanitize_comments_html(toc)
                comments += '<h3>[목차]</h3><div id="toc">' + toc + "</div>"
            
        return comments

    def parse_cover(self, root):
        # <meta property="og:image" content="http://image.kyobobook.co.kr/images/book/xlarge/547/x9780132990547.jpg"/>
        imgcol_node = root.xpath('//meta[@property="og:image"]/@content')
        img_url_checked = None
        if imgcol_node:
            img_url = imgcol_node[0]
            
            # http://image.kyobobook.co.kr/newimages/apps/b2b_academy/common/noimage_150_215.gif
            if not "noimage" in img_url :
                try:
                    # Unfortunately Kyobobook sometimes have broken links so we need to do
                    # an additional request to see if the URL actually exists
                    info = self.browser.open_novisit(img_url, timeout=self.timeout).info()
                    if int(info.getheader('Content-Length')) > 1000:
                        img_url_checked = img_url
                    else:
                        self.log.warning('Broken image(Large) for url: %s'%img_url)
                except:
                    pass
        if not img_url_checked:
            imgcol_node = root.xpath('//p[@class="book_img_box"]/img/@src')
            if imgcol_node:
                img_url = imgcol_node[0]
                
                # http://image.kyobobook.co.kr/newimages/apps/b2b_academy/common/noimage_150_215.gif
                if not "noimage" in img_url :
                    try:
                        # Unfortunately Kyobobook sometimes have broken links so we need to do
                        # an additional request to see if the URL actually exists
                        info = self.browser.open_novisit(img_url, timeout=self.timeout).info()
                        if int(info.getheader('Content-Length')) > 1000:
                            img_url_checked = img_url
                        else:
                            self.log.warning('Broken image(small) for url: %s'%img_url)
                    except:
                        pass
        if img_url_checked:
            return img_url_checked

    def parse_isbn(self, root):
        isbn_node = root.xpath('//div[@class="book_info_basic2"]')
        if isbn_node:
            match = re.search("isbn(?:\-13)?\s?:\s?([^\s]*)",isbn_node[0].text_content(),re.I)
            if match:
                return match.group(1)

    def parse_publisher_and_date(self, root):
        # Publisher is specified within the a :
        #  <a class="np_af" href="/search/wsearchresult.aspx?PublisherSearch=%b4%d9%b9%ae@876&BranchType=1">다문</a> | 2009-09-20
        publisher = None
        pub_date = None
        publisher_node = root.xpath("//span[@title='%s']" % u'출판사')
        if publisher_node:
            # /search/SearchCommonMain.jsp?vPstrCategory=KOR&vPoutSearch=1&vPpubCD=04129&vPsKeywordInfo=실천문학사
            # /search/SearchEngbookMain.jsp?vPstrCategory=ENG&vPoutSearch=1&vPejkGB=BNT&vPpubNM=Prentice Hall&vPsKeywordInfo=Prentice Hall
            publisher_link = publisher_node[0].xpath(".//a")
            if publisher_link:
                publisher = publisher_link[0].text_content()

            # Now look for the pubdate. There should always be one at start of the string
            pubdate_node = publisher_node[0].getparent().xpath(".//span[@class='date']")
            if pubdate_node :
                pubdate_text_str = pubdate_node[0].text_content().strip()
                pubdate_text_match = re.search('(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)', pubdate_text_str)
                if pubdate_text_match is not None:
                    pubdate_text = pubdate_text_match.group(1)
                    if pubdate_text:
                        pub_date = self._convert_date_text_name(pubdate_text)
        return (publisher, pub_date)

    def parse_tags(self, root):
        # Kyobobook have both"tags" and Genres(category)
        # We will use those as tags (with a bit of massaging)
        
        calibre_tags = list()
        
        category_lookup = cfg.plugin_prefs[cfg.STORE_NAME][cfg.KEY_GET_CATEGORY]
        
        if category_lookup:
            genres_node = root.xpath('//div[@class="book_info"]/div[@class="belong_area"]/ul[@class="locate"]/li')
            #self.log.info("Parsing categories")
            if genres_node:
                #self.log.info("Found genres_node")
                for genre in genres_node:
                    genre = re.sub("\s{2,}"," ",genre.text_content().strip())
                    calibre_tags.append("[" + genre + "]")
                
                
        # tags_list = root.xpath('//div[@id="div_itemtaglist"]//a[contains(@href,"tagname=")]/text()')
        # #self.log.info("Parsing tags")
        # if tags_list:
            # #self.log.info("Found tags")
            
            # convert_tag_lookup = cfg.plugin_prefs[cfg.STORE_NAME][cfg.KEY_CONVERT_TAG]
            # if convert_tag_lookup:
                # tags = self._convert_genres_to_calibre_tags(tags_list)
            # else:
                # tags = tags_list
            # if len(tags) > 0:
                # # return calibre_tags
                # calibre_tags.extend(tags)
                
        return calibre_tags

    def _convert_genres_to_calibre_tags(self, genre_tags):
        # for each tag, add if we have a dictionary lookup
        calibre_tag_lookup = cfg.plugin_prefs[cfg.STORE_NAME][cfg.KEY_GENRE_MAPPINGS]
        calibre_tag_map = dict((k.lower(),v) for (k,v) in calibre_tag_lookup.iteritems())
        tags_to_add = list()
        for genre_tag in genre_tags:
            tags = calibre_tag_map.get(genre_tag.lower(), None)
            if tags:
                for tag in tags:
                    if tag not in tags_to_add:
                        tags_to_add.append(tag)
        # return list(tags_to_add)
        return tags_to_add

    def _convert_date_text(self, date_text):
        # Note that the date text could be "2003", "December 2003" or "December 10th 2003"
        year = int(date_text[-4:])
        month = 1
        day = 1
        if len(date_text) > 4:
            text_parts = date_text[:len(date_text)-5].partition(' ')
            month_name = text_parts[0]
            # Need to convert the month name into a numeric value
            # For now I am "assuming" the Kyobobook website only displays in English
            # If it doesn't will just fallback to assuming January
            month_dict = {"January":1, "February":2, "March":3, "April":4, "May":5, "June":6,
                "July":7, "August":8, "September":9, "October":10, "November":11, "December":12}
            month = month_dict.get(month_name, 1)
            if len(text_parts[2]) > 0:
                day = int(re.match('([0-9]+)', text_parts[2]).groups(0)[0]) 
        from calibre.utils.date import utc_tz
        return datetime.datetime(year, month, day, tzinfo=utc_tz)

    def _convert_date_text_name(self, date_text):
        # 2014년 03월 20일 to datetime
        year = 2014
        month = 1
        day = 1
        #dates = re.search("(?P<year>\d{4})년\s*(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일",date_text)
        dates = re.search("(\d{4})년",date_text)
        if dates:
            year = int(dates.group(1))
            dates = re.search("(\d{1,2})월",date_text)
            if dates:
                month = int(dates.group(1))
                dates = re.search("(\d{1,2})일",date_text)
                if dates: 
                    day = int(dates.group(1))
        else:
            return None

        from calibre.utils.date import utc_tz
        return datetime.datetime(year, month, day, tzinfo=utc_tz)

    # Defalut language is Korean at Kyobobook. 
    # Kyobobook 에서 언어를 찾을 수 없을 때
    # 기본 언어로 Korean 을 넣는다.
    def _parse_language(self, root):
        lang_node = root.xpath('//div[@class="book_info_basic2"]')
        if lang_node:
            match = re.search("%s\s?:\s?([^\s]*)" % u'언어',lang_node[0].text_content(),re.I)
            if match:
                raw = match.group(1)
            else:
                raw = "Korean"
            ans = self.lang_map.get(raw, None)
            if ans:
                return ans
            ans = canonicalize_lang(ans)
            if ans:
                return ans

    def _removeTags(self, element, tags):
        try:
            for node in element.getchildren():
                if node.tag in tags:
                    element.remove(node)
                else:
                    self._removeTags(node,tags)
        except:
            return
            
