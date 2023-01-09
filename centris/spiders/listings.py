import scrapy
from scrapy_splash import SplashRequest
from scrapy.selector import Selector
from w3lib.http import basic_auth_header
from urllib.parse import urljoin
import json


class ListingsSpider(scrapy.Spider):
    name = 'listings'
    allowed_domains = ['www.centris.ca']

    position = {
        'startPosition':0
    }

    script = '''
        function main(splash, args)
            splash:on_request(function(request)
                if request.url.find("css")then
                    request.abort()
                end
            end)
            splash.images_enabled = false
            splash.js_enabled = false
            assert(splash:go(args.url))
            assert(splash:wait(0.5))
            return splash:html()
        end
    '''

    handle_httpstatus_list = [555]

    def start_requests(self):
        yield scrapy.Request(
            url='https://www.centris.ca/UserContext/Lock',
            method='POST',
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en',
                'x-requested-with': 'XMLHttpRequest',
                'content-type': 'application/json'
            },
            body=json.dumps({'uc': 0}),
            callback=self.generate_uck
        )
 
    def generate_uck(self, response):
        uck = response.body
        print("uck", uck)

        query = {
            "query": {
                "UseGeographyShapes": 0,
                "Filters": [
                    {
                        "MatchType": "GeographicArea",
                        "Text": "Montréal (Island)",
                        "Id": "GSGS4621"
                    }
                ],
                "FieldsValues": [
                    {
                        "fieldId": "GeographicArea",
                        "value": "GSGS4621",
                        "fieldConditionId": "",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "Category",
                        "value": "Residential",
                        "fieldConditionId": "",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "SellingType",
                        "value": "Sale",
                        "fieldConditionId": "",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "LandArea",
                        "value": "SquareFeet",
                        "fieldConditionId": "IsLandArea",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "SalePrice",
                        "value": 0,
                        "fieldConditionId": "ForSale",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "SalePrice",
                        "value": 1500000,
                        "fieldConditionId": "ForSale",
                        "valueConditionId": ""
                    }
                ]
            },
            "isHomePage": True
        }
        yield scrapy.Request(
            url='https://www.centris.ca/property/UpdateQuery',
            method='POST',
            body=json.dumps(query),
            headers={
                'Content-Type': 'application/json',
                'x-requested-with': 'XMLHttpRequest',
                'x-centris-uc': 0,
                'x-centris-uck': uck
            },
            meta={
                'uck': uck
            },
            callback=self.update_query
        )

    def update_query(self, response):
        uck = response.meta['uck']
        yield scrapy.Request(
            url =  "https://www.centris.ca/Property/GetInscriptions",
            method = "POST",
            body = json.dumps(self.position),
            headers = {
                'Content-Type':'application/json',
                'x-centris-uc': 0,
                'x-centris-uck': uck
            },
            callback=self.parse
        )

    def parse(self, response):
        auth = basic_auth_header('user', 'userpass')

        resp_dict = json.loads(response.body)
        html = resp_dict.get('d').get('Result').get('html')

        sel = Selector(text=html)
        listings = sel.xpath("//div[@class='property-thumbnail-item thumbnailItem col-12 col-sm-6 col-md-4 col-lg-3']/div[@class='shell']")

        for listing in listings:
            category = listing.xpath('normalize-space(.//span[@class="category"]/div/text())').get()
            price = listing.xpath(".//div[@class='price']/span/text()").get()
            price_format = price.replace('\xa0', ',')
            address= ", ".join(listing.xpath(".//span[@class='address']/div/text()").getall())
            beds = listing.xpath(".//div[@class='cac']/text()").get()
            baths = listing.xpath(".//div[@class='sdb']/text()").get()
            url = listing.xpath(".//a[@class='a-more-detail']/@href").get().replace('/fr/', '/en/')
            abs_url = urljoin(base="https://www.centris.ca", url=url)
            print(abs_url)

            # yield {
            #     'category':category,
            #     'price':price_format,
            #     'address':address,
            #     'beds':beds,
            #     'baths':baths,
            #     'link':summary
            # }

            yield  SplashRequest (
                url = abs_url,
                endpoint='execute',
                callback=self.parse_summary,
                args={
                    'lua_source':self.script
                },
                splash_headers={'Authorization': auth},
                meta={
                    'cat':category,
                    'pri':price_format,
                    'addr':address,
                    'beds': beds,
                    'baths': baths,
                    'url':abs_url,
                }
            )
        
        # check total number of estates, increment by from json and then request every next page
        total_count = resp_dict.get("d").get("Result").get("count")
        increment_by = resp_dict.get("d").get("Result").get("inscNumberPerPage")

        
        if self.position["startPosition"] <= total_count:
            self.position["startPosition"] += increment_by
            print(total_count)
            print (self.position)
            yield scrapy.Request(
                url="https://www.centris.ca/Property/GetInscriptions",
                method="POST",
                body=json.dumps(self.position),
                headers={
                        "Content-Type": "application/json",
                        "accept-language": "en-US,en"
                },
                callback=self.parse
                )

        # with open('index.html',mode='w') as file:
        #     file.write(html)


    def parse_summary(self,response):
        address = response.xpath("//h2[@itemprop='address']/text()").get()
        description = response.xpath("normalize-space(//div[@itemprop='description']/text())").get()
        category=response.request.meta['cat']
        price = response.request.meta['pri']
        beds = response.request.meta['beds']
        baths = response.request.meta['baths']
        url=response.request.meta['url']

        yield {
                'address':address,
                'description':description,
                'category':category,
                'price':price,
                'beds':beds,
                'baths':baths,
                'link':url
            }