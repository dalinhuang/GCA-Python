#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

from gca.core import Abstract
from mako.template import Template

import sys
import argparse
import json
import codecs
from gca.tex import basic_tempate
from gca.tex import mk_tex_text

text_replacements = {
    'body': {
        '': '',
    },
    'input': {}
}


def text_replace_all(text, replacements):
    if replacements is not None and text is not None:
        for key, val in replacements.iteritems():
            text = text.replace(key, val)

    return text


def sanitize_abstract(abstract, replacements=None):
    text = text_replace_all(abstract.text, replacements['body'])
    text = mk_tex_text(text, is_body=True)
    abstract.text = text
    return abstract


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GCA Client')
    parser.add_argument('-r', '--replacements', type=str)
    parser.add_argument('file', type=str, default='-')

    args = parser.parse_args()

    if args.replacements is not None:
        with codecs.open(args.replacements, 'r', encoding='utf-8') as r_file:
            r_data = json.loads(r_file.read(), encoding='utf-8')
            for key in r_data.iterkeys():
                text_replacements[key].update(r_data[key])

    fd = codecs.open(args.file, 'r', encoding='utf-8') if args.file != '-' else sys.stdin
    sys.stderr.write('[I] Loading abstract data\n')
    txt = fd.read()
    sys.stderr.write('[I] Pre-processing abstracts\n')
    txt = text_replace_all(txt, text_replacements['input'])
    data = json.loads(txt)
    abstracts = [sanitize_abstract(Abstract(abstract), text_replacements) for abstract in data]
    abstracts = filter(lambda x: x.state == 'Submitted', abstracts)
    abstracts = sorted(abstracts, key=lambda a: a.authors[0].last_name)
    sys.stderr.write('[I] %d abstracts. Generating tex\n' % len(abstracts))

    tex_template = Template(basic_tempate, output_encoding='utf-8')
    rendered = tex_template.render(abstracts=abstracts)
    sys.stderr.write('[I] Done\n')
    sys.stdout.write(rendered)
