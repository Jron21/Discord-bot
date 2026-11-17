import unittest

import main


class XiaohongshuImageExtractionTests(unittest.TestCase):
    def test_extracts_nested_rednote_image_urls(self):
        page = r'''<script>window.__INITIAL_STATE__={"noteData":{"imageList":[
            {"url":"http:\u002F\u002Fsns-web-i10.rednotecdn.com\u002Fimg\u002Fone?format=preview",
             "infoList":[
                {"url":"http:\u002F\u002Fsns-web-i10.rednotecdn.com\u002Fimg\u002Fone?format=preview","imageScene":"H5_PRV"},
                {"url":"http:\u002F\u002Fsns-web-i10.rednotecdn.com\u002Fimg\u002Fone?format=detail","imageScene":"H5_DTL"}
             ]},
            {"url":"https:\u002F\u002Fsns-web-i10.rednotecdn.com\u002Fimg\u002Ftwo?format=jpg"}
        ]}}</script>'''

        urls = main.extract_xiaohongshu_image_urls(page)

        self.assertEqual(
            urls,
            [
                "https://sns-web-i10.rednotecdn.com/img/one?format=detail",
                "https://sns-web-i10.rednotecdn.com/img/two?format=jpg",
            ],
        )

    def test_ignores_urls_outside_xiaohongshu_cdns(self):
        page = (
            '{"imageList":[{"url":"https://example.com/image.jpg"},'
            '{"url":"https://sns-img.xhscdn.com/image/one"}]}'
        )

        self.assertEqual(
            main.extract_xiaohongshu_image_urls(page),
            ["https://sns-img.xhscdn.com/image/one"],
        )


if __name__ == "__main__":
    unittest.main()
