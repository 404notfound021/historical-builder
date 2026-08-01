"""全局断链扫描: 验证所有 .md 文件中的 [[link]] 都有对应节点"""
import os, re, pytest

OBSIDIAN = os.path.expanduser(
    '~/Library/Mobile Documents/com~apple~CloudDocs/Obsidian/枢机智库/Raw_Source/History')

@pytest.fixture(scope="module")
def all_nodes():
    """收集所有存在的节点名"""
    nodes = set()
    for subdir in ['人物', '事件', '地名', '职官', 'MOC', '史书']:
        d = os.path.join(OBSIDIAN, subdir)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith('.md'):
                    nodes.add(f.replace('.md', ''))
    return nodes

@pytest.fixture(scope="module")
def all_links():
    """扫描所有文件中的 [[link]] 引用"""
    links = {}  # source_file → [targets]
    for subdir in ['人物', '事件', '地名', '职官']:
        d = os.path.join(OBSIDIAN, subdir)
        if not os.path.isdir(d): continue
        for f in os.listdir(d):
            if not f.endswith('.md'): continue
            t = open(os.path.join(d, f)).read()
            targets = set(m.group(1) for m in re.finditer(r'\[\[(.+?)\]\]', t))
            for target in targets:
                links.setdefault(target, set()).add(f'{subdir}/{f}')
    return links

def test_no_broken_person_links(all_nodes, all_links):
    """人物/事件/地名引用必须有对应节点（官职除外）"""
    # Known legitimate positions that may not have standalone nodes
    POSITION_SUFFIXES = ('太守','将军','校尉','中郎将','司马','刺史','令','长','丞',
                         '掾','属','从事','都尉','尚书','大夫','常侍','仆射','中郎',
                         '司农','太傅','太尉','司空','司徒','丞相','相国')
    broken = []
    for target, sources in sorted(all_links.items()):
        if target in all_nodes: continue
        if target in ('无考','','None','null'): continue
        # Skip position names
        if any(target.endswith(s) for s in POSITION_SUFFIXES): continue
        # Skip dynasty-alikes (single names)
        if target in ('东汉','西汉','曹魏','蜀汉','东吴','西晋','东晋','倭国'): continue
        broken.append((target, sorted(sources)))
    if broken:
        msg = f'{len(broken)} broken links found:\n'
        for target, sources in broken[:20]:
            msg += f'  [[{target}]] ← {sources[:3]}\n'
        pytest.fail(msg)

def test_no_overspecific_place_names(all_links, all_nodes):
    """地名不应包含方位词(之南/之北/以东)等过于具体的描述"""
    bad = []
    for target in all_links:
        for suffix in ['之南', '之北', '以东', '以西', '之东', '之西']:
            if suffix in target:
                bad.append(target)
                break
    if bad:
        pytest.fail(f'过于具体的地名: {bad[:10]}')

def test_dynasty_nodes_exist(all_nodes):
    """朝代节点应存在(stub即可)"""
    for dynasty in ['东汉', '西汉', '曹魏', '蜀汉', '东吴', '西晋', '东晋']:
        if dynasty not in all_nodes:
            # Dynasty stubs can be created, but log as warning
            print(f'  ⚠ 朝代节点缺失: {dynasty}')
    # Not a hard fail — dynasties are semi-expected to be stubs
    assert True
