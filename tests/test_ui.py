import os
import tempfile
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from src import api as c


class ScreenTests(unittest.TestCase):
    def test_six_screens_and_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp)/'ui.db')
            previous = os.environ.get('MY_AI_ASSET_DB')
            os.environ['MY_AI_ASSET_DB'] = path
            try:
                db=c.connect(path)
                c.seed(db)
                db.close()
                app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run(timeout=30)
                self.assertFalse(app.exception)
                self.assertEqual(next(m for m in app.metric if m.label=='保有資産の評価額').value,'82,500 円')
                for page in ['2_保有資産.py','6_データ管理.py','3_積立プラン.py','4_AI分析.py','5_資産シミュレーション.py','1_ホーム.py']:
                    app.switch_page('pages/' + page).run(timeout=30)
                    self.assertFalse(app.exception,msg=page)
                app.switch_page('pages/1_ホーム.py').run()
                next(b for b in app.button if b.label == '現在の資産状況を履歴に保存').click().run()
                self.assertFalse(app.exception)
                app.switch_page('pages/2_保有資産.py').run()
                next(t for t in app.text_input if t.label=='銘柄名').set_value('編集済み・架空ファンド')
                next(b for b in app.button if b.label == '登録内容を保存').click().run()
                self.assertFalse(app.exception)
                db=c.connect(path)
                self.assertEqual(c.holdings(db)[0]['name'],'編集済み・架空ファンド')
                self.assertEqual(len(c.snapshots(db)),1)
                db.close()
                app.switch_page('pages/6_データ管理.py').run()
                next(t for t in app.text_input if t.label=='銘柄名').set_value('テスト投信')
                app.number_input[0].set_value(10000)
                app.number_input[1].set_value(12000)
                app.number_input[3].set_value(10000)
                next(b for b in app.button if b.label == '保有残高を追加').click().run()
                self.assertFalse(app.exception)
                db=c.connect(path)
                self.assertEqual(len(c.holdings(db)),4)
                db.close()
            finally:
                if previous is None:
                    os.environ.pop('MY_AI_ASSET_DB',None)
                else:
                    os.environ['MY_AI_ASSET_DB']=previous


if __name__=='__main__':
    unittest.main()
