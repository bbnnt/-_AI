# -*- coding: utf-8 -*-
"""临时修复脚本：修复 main.js 中 escapeHtml 被 HTML 解码的实体"""
p = 'static/js/main.js'
s = open(p, encoding='utf-8').read()

amp = chr(38)  # & 字符，避免被 HTML 解码
fixes = [
    (".replace(/&/g, '" + amp + "')", ".replace(/&/g, '" + amp + "amp;')"),
    (".replace(/</g, '<')", ".replace(/</g, '" + amp + "lt;')"),
    (".replace(/>/g, '>')", ".replace(/>/g, '" + amp + "gt;')"),
    ('.replace(/"/g, \'"\')', '.replace(/"/g, \'' + amp + 'quot;\')'),
]
count = 0
for old, new in fixes:
    if old in s:
        s = s.replace(old, new)
        count += 1
open(p, 'w', encoding='utf-8').write(s)
print('fixed', count, 'of', len(fixes))