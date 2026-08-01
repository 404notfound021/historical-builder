---
type: faction
faction_name: {{faction_name}}
dynasty: "[[{{dynasty}}]]"
period: {{period}}
founder: "[[{{founder}}]]"
key_members:
  {% for m in key_members %}
  - "[[{{m}}]]"
  {% endfor %}
capital: {{capital}}
source_book: "[[{{source_book}}]]"
tags:
  - "#势力阵营"
created: {{created}}
modified: {{modified}}
---
# {{faction_name}}

## 概述

{{summary}}

## 建立与发展

{{history}}

## 核心人物

{{core_figures}}

## 势力范围

{{territory}}

## 消亡

{{decline}}
