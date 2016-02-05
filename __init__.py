#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2014, YongSeok Choi <sseeookk@gmail.com> based on the Goodreads work by Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

import time, re
from urllib import quote
from Queue import Queue, Empty
from collections import OrderedDict

from lxml.html import fromstring, tostring

from calibre import as_unicode
from calibre.ebooks.metadata import check_isbn
from calibre.ebooks.metadata.sources.base import Source
from calibre.utils.icu import lower
from calibre.utils.cleantext import clean_ascii_chars

class Kyobobook(Source):
    '''
    This plugin is only for books in the Korean language.
    It allows Calibre to read book information from kyobobook(online book store in korea, http://kyobobook.co.kr/) when you choose to download/fetch metadata.
    It was based on the 'Goodreads' and the 'Barnes' by 'Grant Drake'.
    '''
    name = 'KyoboBook'
    description = _('Downloads metadata and covers from kyobobook.co.kr')
    author = 'YongSeok Choi'
    version = (0, 2, 0)
    minimum_calibre_version = (0, 8, 0)

    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'identifier:kyobobook',
        'identifier:isbn', 'rating', 'comments', 'publisher', 'pubdate',
        'tags', 'series', 'languages'])
    has_html_comments = True
    supports_gzip_transfer_encoding = True

    # 201403 kyobobook url patterns :
    # http://www.kyobobook.co.kr/search/SearchCommonMain.jsp?vPstrCategory=TOT&vPplace=top&vPstrKeyWord=
    # 국내도서
    # http://www.kyobobook.co.kr/product/detailViewKor.laf?barcode=9788936472016
    # 외국도서
    # http://www.kyobobook.co.kr/product/detailViewEng.laf?barcode=9788936472016
    
    BASE_URL = 'http://www.kyobobook.co.kr'
    
    def config_widget(self):
        '''
        Overriding the default configuration screen for our own custom configuration
        '''
        from calibre_plugins.kyobobook.config import ConfigWidget
        return ConfigWidget(self)

    def get_book_url(self, identifiers):
        kyobobook_id = identifiers.get('kyobobook', None)
        if kyobobook_id:
            return ('kyobobook', kyobobook_id, '%s/product/detailViewKor.laf?barcode=%s' % (Kyobobook.BASE_URL, kyobobook_id))

    def create_query(self, log, title=None, authors=None, identifiers={}):

        isbn = check_isbn(identifiers.get('isbn', None))
        # http://www.kyobobook.co.kr/search/SearchCommonMain.jsp?vPstrCategory=TOT&vPplace=top&vPstrKeyWord=9788936472016
        q = ''
        if isbn is not None:
            q = '/search/SearchCommonMain.jsp?vPstrCategory=TOT&vPplace=top&vPstrKeyWord=' + isbn
            # q = '/shop/wproduct.aspx?ISBN=' + isbn
            
        elif title or authors:
            
            tokens = []
            
            title_tokens = list(self.get_title_tokens(title, strip_joiners=False, strip_subtitle=True))
            # tokens += title_tokens
            tokens += [quote(t.encode('euc-kr') if isinstance(t, unicode) else t) for t in title_tokens] # kyobobook by sseeookk
            
            # TODO: No tokent is returned for korean name.
            # 한글이름일 경우 token 이 반환 안된다.
            # by sseeookk ,  20140315 
            # author_tokens = self.get_author_tokens(authors, only_first_author=True)
            authors_encode = None
            if authors : authors_encode = list(a.encode('utf-8') for a in authors)
            author_tokens = self.get_author_tokens(authors_encode, only_first_author=True)
            # tokens += author_tokens
            
            # tokens = [quote(t.encode('utf-8') if isinstance(t, unicode) else t) for t in tokens]
            tokens += [quote(t.encode('euc-kr') ) for t in author_tokens] # kyobobook by sseeookk
            
            q = '+'.join(tokens)
            
            q = '/search/SearchCommonMain.jsp?vPstrCategory=TOT&vPplace=top&vPstrKeyWord=' + q
            
        if not q:
            return None
        # by sseeookk
        # if isinstance(q, unicode):
            # q = q.encode('utf-8')
        return Kyobobook.BASE_URL + '' + q
    
    def get_cached_cover_url(self, identifiers):
        url = None
        kyobobook_id = identifiers.get('kyobobook', None)
        if kyobobook_id is None:
            isbn = identifiers.get('isbn', None)
            if isbn is not None:
                kyobobook_id = self.cached_isbn_to_identifier(isbn)
        if kyobobook_id is not None:
            url = self.cached_identifier_to_cover_url(kyobobook_id)
        
        return url

    def identify(self, log, result_queue, abort, title=None, authors=None, identifiers={}, timeout=30):
        '''
        Note this method will retry without identifiers automatically if no
        match is found with identifiers.
        '''
        matches = []
        # Unlike the other metadata sources, if we have a kyobobook id then we
        # do not need to fire a "search" at kyobobook.com. Instead we will be
        # able to go straight to the URL for that book.
        kyobobook_id = identifiers.get('kyobobook', None)
        isbn = check_isbn(identifiers.get('isbn', None))
        br = self.browser
        if kyobobook_id:
            matches.append('%s/product/detailViewKor.laf?barcode=%s' % (Kyobobook.BASE_URL, kyobobook_id))
        else:
            query = self.create_query(log, title=title, authors=authors, identifiers=identifiers)
            if query is None:
                log.error('Insufficient metadata to construct query')
                return
            try:
                log.info('Querying: %s' % query)
                response = br.open_novisit(query, timeout=timeout)
                
                try:
                    raw = response.read().strip()
                    # open('E:\\t11.html', 'wb').write(raw) # XXXX
                    
                    # by sseeookk
                    # euc-kr at kyobobook
                    # raw = raw.decode('utf-8', errors='replace')
                    raw = raw.decode('euc-kr', errors='replace')
                    if not raw:
                        log.error('Failed to get raw result for query: %r' % query)
                        return
                    root = fromstring(clean_ascii_chars(raw))
                except:
                    msg = 'Failed to parse kyobobook page for query: %r' % query
                    log.exception(msg)
                    return msg
                
                if isbn:
                    self._parse_search_isbn_results(log, isbn, root, matches, timeout)
                
                # For ISBN based searches we have already done everything we need to
                # So anything from this point below is for title/author based searches.
                if not isbn:
                    # Now grab the first value from the search results, provided the
                    # title and authors appear to be for the same book
                    self._parse_search_results(log, title, authors, root, matches, timeout)
                    
            except Exception as e:
                err = 'Failed to make identify query: %r' % query
                log.exception(err)
                return as_unicode(e)


        if abort.is_set():
            return

        if not matches:
            if identifiers and title and authors:
                log.info('No matches found with identifiers, retrying using only'
                        ' title and authors')
                return self.identify(log, result_queue, abort, title=title,
                        authors=authors, timeout=timeout)
            log.error('No matches found with query: %r' % query)
            return
        
        
        from calibre_plugins.kyobobook.worker import Worker
        workers = [Worker(url, result_queue, br, log, i, self) for i, url in enumerate(matches)]
        
        for w in workers:
            w.start()
            # Don't send all requests at the same time
            time.sleep(0.1)

        while not abort.is_set():
            a_worker_is_alive = False
            for w in workers:
                w.join(0.2)
                if abort.is_set():
                    break
                if w.is_alive():
                    a_worker_is_alive = True
            if not a_worker_is_alive:
                break

        return None

    def _parse_search_isbn_results(self, log, orig_isbn, root, matches, timeout):
        results = root.xpath('//ul[contains(@class, "domestic") or contains(@class, "abroad")]')
        if not results:
            #log.info('FOUND NO RESULTS:')
            return

        import calibre_plugins.kyobobook.config as cfg
        max_results = cfg.plugin_prefs[cfg.STORE_NAME][cfg.KEY_MAX_DOWNLOADS]
        title_url_map = OrderedDict()
        num = 1
        for result in results:
            log.info('Looking at result:')
            title_nodes = result.xpath('./li[contains(@class,"title")]/a[contains(@href,"/product/detailView")]')
            
            title = ''
            if title_nodes:
                title = title_nodes[0].text_content().strip()
            if not title:
                log.info('Could not find title')
                continue
            # Strip off any series information from the title
            log.info('FOUND TITLE:',title)
            if '(' in title:
                #log.info('Stripping off series(')
                title = title.rpartition('(')[0].strip()
            
            result_url = title_nodes[0].get('href')
            
            # if result_url and title not in title_url_map:
                # title_url_map[title] = Kyobobook.BASE_URL + result_url
            if result_url :
                title_url_map["[%d] %s" % (num, title)] = Kyobobook.BASE_URL + result_url
                num = num + 1
                if len(title_url_map) >= max_results:
                    break
        
        for title in title_url_map.keys():
            matches.append(title_url_map[title])
            if len(matches) >= max_results:
                break


    def _parse_search_results(self, log, orig_title, orig_authors, root, matches, timeout):
        results = root.xpath('//ul[contains(@class, "domestic") or contains(@class, "abroad")]')
        if not results:
            #log.info('FOUND NO RESULTS:')
            return

        title_tokens = list(self.get_title_tokens(orig_title))
        # by sseeookk, 20140315
        # for korean author name
        # author_tokens = list(self.get_author_tokens(orig_authors))
        orig_authors_encode = None
        if orig_authors : orig_authors_encode = list(a.encode('utf-8') for a in orig_authors) # by sseeookk
        author_tokens = list(self.get_author_tokens(orig_authors_encode))
            
        def ismatch(title, authors):
            authors = lower(' '.join(authors))
            title = lower(title)
            match = not title_tokens
            for t in title_tokens:
                if lower(t) in title:
                    match = True
                    break
            amatch = not author_tokens
            for a in author_tokens:
                if lower(a) in authors:
                    amatch = True
                    break
            if not author_tokens: amatch = True
            return match and amatch

        import calibre_plugins.kyobobook.config as cfg
        max_results = cfg.plugin_prefs[cfg.STORE_NAME][cfg.KEY_MAX_DOWNLOADS]
        title_url_map = OrderedDict()
        num = 1
        for result in results:
            log.info('Looking at result:')
            title_nodes = result.xpath('./li[contains(@class,"title")]/a[contains(@href,"/product/detailView")]')
            
            title = ''
            if title_nodes:
                title = re.sub("\s{2,}"," ",title_nodes[0].text_content().strip())
            if not title:
                log.info('Could not find title')
                continue
            # Strip off any series information from the title
            # log.info('\nFOUND TITLE:',title)
            log.info('\nFOUND TITLE:',title.encode('euc-kr')) # by sseeookk
            if '(' in title:
                #log.info('Stripping off series(')
                title = title.rpartition('(')[0].strip()

            contributors = result.xpath('.//a[@class="author"]')
            authors = []
            for c in contributors:
                author = c.text_content()
                #log.info('Found author:',author)
                if author:
                    authors.append(author.strip())
            
            #log.info('Looking at tokens:',author)
            #log.info('Considering search result: %s %s' % (title, authors)) 
            log.info('Considering search result: ' , title.encode('euc-kr') ,",", '|'.join(authors).encode('euc-kr')) 
            if not ismatch(title, authors):
                #log.error('Rejecting as not close enough match: %s %s' % (title, authors))
                log.error('Rejecting as not close enough match: ' , title.encode('euc-kr') ,",", '|'.join(authors).encode('euc-kr'))
                continue

            result_url = title_nodes[0].get('href')
            
            # if result_url and title not in title_url_map:
                # title_url_map[title] = Kyobobook.BASE_URL + result_url
            if result_url :
                title_url_map["[%d] %s" % (num, title)] = Kyobobook.BASE_URL + result_url
                num = num + 1
                if len(title_url_map) >= max_results:
                    break
        
        for title in title_url_map.keys():
            matches.append(title_url_map[title])
            if len(matches) >= max_results:
                break

    def download_cover(self, log, result_queue, abort,
            title=None, authors=None, identifiers={}, timeout=30):
        cached_url = self.get_cached_cover_url(identifiers)
        if cached_url is None:
            log.info('No cached cover found, running identify')
            rq = Queue()
            self.identify(log, rq, abort, title=title, authors=authors, identifiers=identifiers)
            if abort.is_set():
                return
            results = []
            while True:
                try:
                    results.append(rq.get_nowait())
                except Empty:
                    break
            results.sort(key=self.identify_results_keygen(title=title, authors=authors, identifiers=identifiers))
            for mi in results:
                cached_url = self.get_cached_cover_url(mi.identifiers)
                if cached_url is not None:
                    break
        if cached_url is None:
            log.info('No cover found')
            return

        if abort.is_set():
            return
        br = self.browser
        log('Downloading cover from:', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            log.exception('Failed to download cover from:', cached_url)


if __name__ == '__main__': # tests
    # To run these test use:
    # calibre-debug -e __init__.py
    from calibre.ebooks.metadata.sources.test import (test_identify_plugin,
            title_test, authors_test, series_test)
    
    test_identify_plugin(Kyobobook.name,
        [
            # 원제 꼭지가 붙어 있다.
            # 장 코르미에 (지은이) | 김미선 (옮긴이) | 실천문학사 | 2005-05-25 | 원제 Che Guevara (2002년) 
            (# A book with an ISBN
                {'identifiers':{'isbn': '9788939205109'},
                    'title':'체 게바라', 'authors':['장 코르미에']},
                [title_test('체 게바라 평전', exact=True),
                 authors_test(['장 코르미에','김미선']),
                 series_test('역사인물찾기', 10.0)]
            ),
            
            (# A book with an kyobobook id
                {'identifiers':{'kyobobook': '9788932008486'}},
                [title_test('광장/구운몽', exact=True),
                 authors_test(['최인훈']),
                 ]
            ),
            
            (# A book with title and author
                {'identifiers':{'isbn': '9788936470111'}},
                [title_test('나의 문화유산답사기 1', exact=False),
                 authors_test(['유홍준'])]
            ), # 9788936470111
            
            (# A book with title and author
                {'title':'나의 문화유산답사기 1', 'authors':['유홍준']},
                [title_test('나의 문화유산답사기 1', exact=False),
                 authors_test(['유홍준'])]
            ), # 9788936470111
            
            (# A book with title and author
                {'identifiers':{'isbn': '9788984317475'}},
                [title_test('높고 푸른 사다리', exact=False),
                 authors_test(['공지영'])]
            ), # 9788936470111
            
        ])


