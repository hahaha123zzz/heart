"""A multi-image section must bind every image to the same fresh release."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from knowledge.figures import section_figures


class SectionReleaseBindingTests(unittest.TestCase):
    def test_one_fresh_release_is_shared_by_all_images_in_section(self):
        with patch('knowledge.course_release.binding',return_value={'release_id':'release-one'}) as binding:
            def figure(key,section=1):
                def public(*,release=None):
                    identity=release if release is not None else binding()
                    return {'id':key,'textbook_release':identity['release_id']}
                return SimpleNamespace(kind='image',chapter_id=2,section_id=section,
                    is_valid=lambda:True,public=public)
            with patch('knowledge.figures.load_figures',return_value=(figure('a'),figure('b'),figure('other',2))), \
                 patch('knowledge.figures._visual_kinds',return_value=('image',)):
                rows=section_figures(2,1)
        self.assertEqual(rows,[{'id':'a','textbook_release':'release-one'},{'id':'b','textbook_release':'release-one'}])
        binding.assert_called_once_with()
