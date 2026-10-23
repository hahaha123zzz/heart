import unittest
from tests.test_visual_locations import VisualFixture

class VisualLocationIntegrationTests(VisualFixture, unittest.TestCase):
 def test_api_requires_saved_identity_and_rejects_client_paths(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from web_api import router
  app=FastAPI();app.include_router(router);client=TestClient(app)
  body=dict(asset_id=self.row['id'],sha256=self.row['sha256'],document_id=self.record['document_id'],version=self.version)
  self.assertEqual(client.post('/api/course/figure-location',json=body).json()['status'],'exact')
  self.assertEqual(client.post('/api/course/figure-location',json=body|{'path':'/secret'}).status_code,422)
  self.assertEqual(client.post('/api/course/figure-location',json={'asset_id':self.row['id']}).status_code,422)
 def test_new_answer_saves_exact_reference_without_claiming_pixels_seen(self):
  from types import SimpleNamespace
  from knowledge.answer_media import selected_media
  figure=SimpleNamespace(chapter_id=1,section_id=1,label='Fig1-1',is_valid=lambda:True,public=lambda:dict(id=self.row['id'],sha256=self.row['sha256'],document_id=self.record['document_id'],version=self.version,image_url='/api/figures/'+self.row['id']+'/image',review_status='pending'))
  source=dict(chapter_id=1,section_id=1,document_id=self.record['document_id'],version=self.version,text='not a caption')
  with patch('knowledge.answer_media.get_figure',return_value=figure):item=selected_media('picture',[source],asset_id=self.row['id'])[0]
  self.assertEqual(item['selection_ref']['rects'][0]['page'],2);self.assertEqual(item['location_status'],'exact');self.assertFalse(item['model_saw_pixels']);self.assertEqual(item['review_status'],'pending')

if __name__=='__main__':unittest.main()
