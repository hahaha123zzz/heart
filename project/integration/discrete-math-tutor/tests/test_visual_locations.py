"""原图导航契约：真实临时 PDF/资产；不调用模型，不写教材或学生库。"""
import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import fitz
from PIL import Image, ImageDraw
from knowledge import source_visuals, pdf_reader, visual_locations as locations
from knowledge.figures import load_figures

class VisualFixture:
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.folder=self.root/'chapters/chapter_01';self.folder.mkdir(parents=True)
  self.asset=self.folder/'image.png';image=Image.new('RGB',(200,160),'white');ImageDraw.Draw(image).rectangle((25,30,170,130),outline='black',width=4);image.save(self.asset)
  source=self.folder/'source.docx';source.write_bytes(b'original');self.source_sha=locations.digest(source)
  self.row=dict(id='image-01-0001',filename='image.png',sha256=locations.digest(self.asset),source_sha256=self.source_sha,kind='image',section_id=1,block_index=1,occurrences=[{'block':1}],labels=['Fig1-1'],context='Fig1-1  Caption',source='chapter1.txt',section='Section',review_status='pending')
  (self.folder/'assets.json').write_text(json.dumps([self.row]))
  (self.root/'manifest.json').write_text(json.dumps({'full_import':{'chapters':[{'chapter_id':1,'docx':'chapters/chapter_01/source.docx','source_sha256':self.source_sha}]}}))
  self.pdf=self.folder/'chapter_01.generated.pdf';self.make_pdf()
  self.patches=[patch.object(source_visuals,'PSYCHOLOGY_DIR',self.root),patch.object(pdf_reader,'PSYCHOLOGY_DIR',self.root),patch.object(locations,'REVIEWED',self.root/'reviewed.json')]
  for p in self.patches:p.start()
  self.clear()
 def clear(self):
  source_visuals.clear_cache();load_figures.cache_clear();pdf_reader.documents.cache_clear();locations.pdf_images.cache_clear()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.clear();self.temp.cleanup()
 def make_pdf(self,repeat=False,caption=False,mention=False,include=True):
  pdf=fitz.open()
  for i in range(2):
   page=pdf.new_page(width=500,height=700)
   if (i==1 or repeat) and include:page.insert_image(fitz.Rect(100,200,400,440),filename=self.asset)
   if caption:page.insert_text((100,500),'Fig1-1  Caption')
   if mention:page.insert_text((100,100),'Discussion mentions Fig1-1  Caption')
  pdf.save(self.pdf);pdf.close()
  self.version=locations.digest(self.pdf)
  self.record=dict(course_id='experimental-psychology-3',document_id='experimental-psychology-3:chapter-01',chapter_id=1,version=self.version,source='chapter1.txt',sections=[dict(id=1,title='Section',page=1,y=0,verified=True)],page_count=2)
  (self.root/'pdf_manifest.json').write_text(json.dumps([self.record]))
 def resolve(self,**extra):
  return locations.resolve_figure(**(dict(asset_id=self.row['id'],sha256=self.row['sha256'],document_id=self.record['document_id'],version=self.version)|extra))

class VisualLocationTests(VisualFixture, unittest.TestCase):
 def test_exact_decoded_pixels_and_pending_unchanged(self):
  r=self.resolve();self.assertEqual(r['status'],'exact');self.assertEqual(r['page'],2);self.assertEqual(r['rects'][0]['y1'],200/700);self.assertEqual(r['selection_ref']['kind'],'area');self.assertEqual(r['review_status'],'pending')
 def test_same_pixels_different_file_encoding(self):
  image=Image.open(self.asset);image.save(self.asset,compress_level=0)
  self.row['sha256']=locations.digest(self.asset);(self.folder/'assets.json').write_text(json.dumps([self.row]));self.clear()
  self.assertEqual(self.resolve()['status'],'exact')
 def test_duplicate_is_ambiguous(self):
  self.make_pdf(repeat=True);r=self.resolve();self.assertEqual(r['status'],'ambiguous');self.assertIsNone(r['selection_ref'])
 def test_section_disambiguates_without_changing_target(self):
  self.make_pdf(repeat=True);self.record['sections'].append(dict(id=2,title='Other',page=2,y=0,verified=True));(self.root/'pdf_manifest.json').write_text(json.dumps([self.record]));r=self.resolve();self.assertEqual(r['status'],'exact');self.assertEqual(r['page'],1);self.assertEqual(r['section_id'],1)
 def test_section_mismatch_is_not_silent_reassignment(self):
  self.record['sections'].append(dict(id=2,title='Other',page=2,y=0,verified=True));(self.root/'pdf_manifest.json').write_text(json.dumps([self.record]));self.assertEqual(self.resolve()['status'],'ambiguous')
 def test_caption_only_and_body_mention_not_caption(self):
  self.make_pdf(include=False,mention=True);self.assertEqual(self.resolve()['status'],'section')
  self.make_pdf(include=False,caption=True);self.assertEqual(self.resolve()['status'],'ambiguous')
 def test_single_caption_is_honest_text_reference(self):
  self.make_pdf(include=False);pdf=fitz.open(self.pdf);pdf[1].insert_text((100,500),'Fig1-1  Caption');pdf.saveIncr();self.version=locations.digest(self.pdf);self.record['version']=self.version;(self.root/'pdf_manifest.json').write_text(json.dumps([self.record]));r=self.resolve();self.assertEqual(r['status'],'caption');self.assertEqual(r['selection_ref']['kind'],'text')
 def test_stale_document_hash_and_asset_identity(self):
  self.assertEqual(self.resolve(version='0'*64)['status'],'stale');self.assertEqual(self.resolve(sha256='0'*64)['status'],'stale');self.assertEqual(self.resolve(document_id='other')['status'],'stale')
 def test_replaced_pdf_invalidates_warm_cache(self):
  self.assertEqual(self.resolve()['status'],'exact');self.pdf.write_bytes(b'changed');self.assertEqual(self.resolve()['status'],'stale')
 def test_replaced_asset_or_source_invalidates(self):
  self.assertEqual(self.resolve()['status'],'exact');self.asset.write_bytes(b'changed');self.assertIsNone(self.resolve()['selection_ref'])
 def test_returned_reference_cannot_mutate_cached_pdf_positions(self):
  result=self.resolve();result['rects'][0]['page']=999;self.assertEqual(self.resolve()['page'],2)
 def test_missing_asset(self):
  self.assertEqual(self.resolve(asset_id='image-01-9999')['status'],'unavailable')
 def test_source_changed(self):
  (self.folder/'source.docx').write_bytes(b'changed');self.assertIsNone(self.resolve()['selection_ref'])
 def test_fresh_manifest_not_old_reader_cache(self):
  self.assertIsNotNone(pdf_reader.document(self.record['document_id']));self.record['version']='0'*64;(self.root/'pdf_manifest.json').write_text(json.dumps([self.record]));self.assertEqual(self.resolve()['status'],'stale')
 def test_no_arbitrary_reviewed_rectangles(self):
  (self.root/'reviewed.json').write_text(json.dumps([dict(asset_id=self.row['id'],asset_sha256=self.row['sha256'],document_id=self.record['document_id'],version=self.version,pdf_pixel_sha256='0'*64,rect=dict(page=1,x1=.1,y1=.1,x2=.9,y2=.9))]));self.assertEqual(self.resolve()['page'],2)


 def test_reviewed_transcode_requires_bound_pdf_pixels_and_rect(self):
  scaled=self.folder/'scaled.jpg';Image.open(self.asset).resize((100,80)).save(scaled)
  pdf=fitz.open();page=pdf.new_page(width=500,height=700);page.insert_image(fitz.Rect(100,200,400,440),filename=scaled);pdf.save(self.pdf);pdf.close()
  self.version=locations.digest(self.pdf);self.record['version']=self.version;self.record['page_count']=1;(self.root/'pdf_manifest.json').write_text(json.dumps([self.record]));self.assertEqual(self.resolve()['status'],'section')
  entry=locations.pdf_images(str(self.pdf),self.version)[0]
  mapping=dict(asset_id=self.row['id'],asset_sha256=self.row['sha256'],document_id=self.record['document_id'],version=self.version,pdf_pixel_sha256=entry['pixel_sha256'],rect=dict(entry['rect']))
  (self.root/'reviewed.json').write_text(json.dumps([mapping]));self.assertEqual(self.resolve()['basis'],'reviewed_transcoded_image')
  mapping['rect']['page']=2;(self.root/'reviewed.json').write_text(json.dumps([mapping]));self.assertEqual(self.resolve()['status'],'section')
if __name__=='__main__':unittest.main()
