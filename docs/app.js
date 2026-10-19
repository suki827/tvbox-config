const labels = {live_video:'电视直播',live_audio:'广播直播',vod:'官方点播',podcast:'Podcast',official_link:'官方入口'};
const $ = id => document.getElementById(id);
let catalog = {sources:[], items:[]};
let profile = 'A';
const make = (tag, text, className) => {const node=document.createElement(tag);node.textContent=text;if(className)node.className=className;return node};
const badge = text => make('span',text,'tag');
function choices(select,allLabel,values){select.replaceChildren(new Option(allLabel,'all'),...values.map(value=>new Option(value,value)))}
function refreshFilters(){
  const sources=Object.fromEntries(catalog.sources.map(source=>[source.id,source]));
  const visible=catalog.items.filter(item=>item.profiles.includes(profile));
  const ids=[...new Set(visible.map(item=>item.source_id))].sort((a,b)=>sources[a].name.localeCompare(sources[b].name));
  const source=$('source');source.replaceChildren(new Option('全部来源','all'),...ids.map(id=>new Option(sources[id].name,id)));
  choices($('category'),'全部分类',[...new Set(visible.flatMap(item=>sources[item.source_id].categories))].sort());
  choices($('level'),'全部难度',[...new Set(visible.map(item=>item.learning_level).filter(level=>level&&level!=='unknown'))].sort());
  choices($('learning-type'),'全部学习类型',[...new Set(visible.map(item=>item.learning_type).filter(type=>type&&type!=='unknown'))].sort());
  for(const control of document.querySelectorAll('.learning-filter'))control.hidden=profile!=='B';
  render();
}
function link(text,url,className){const element=make('a',text,className);element.href=url;element.target='_blank';element.rel='noopener noreferrer';return element}
function render(){
  const sources=Object.fromEntries(catalog.sources.map(source=>[source.id,source]));
  const q=$('search').value.trim().toLocaleLowerCase();
  const found=catalog.items.filter(item=>{
    const source=sources[item.source_id];
    return item.profiles.includes(profile)
      && ($('type').value==='all'||item.type===$('type').value)
      && ($('source').value==='all'||item.source_id===$('source').value)
      && ($('category').value==='all'||source.categories.includes($('category').value))
      && (profile!=='B'||$('level').value==='all'||item.learning_level===$('level').value)
      && (profile!=='B'||$('learning-type').value==='all'||item.learning_type===$('learning-type').value)
      && (!q||[item.title,item.description,item.programme,source.name,...source.categories].join(' ').toLocaleLowerCase().includes(q));
  });
  const cards=$('cards');cards.replaceChildren();
  for(const item of found){
    const source=sources[item.source_id], card=make('article','','card');
    card.append(make('div',source.name,'source'),make('h2',item.title));
    if(item.description)card.append(make('p',item.description));
    const tags=make('div','','tags');
    tags.append(badge(labels[item.type]||item.type),badge(source.country),badge(source.nz_access||'NZ_UNVERIFIED'));
    if(source.availability_regions==='NZ')tags.append(badge('仅限新西兰服务'));
    if(source.availability_regions==='US')tags.append(badge('美国权益限制'));
    if(source.availability_regions==='international_live')tags.append(badge('官网国际直播'));
    const requirement=source.access_requirements;
    tags.append(badge(requirement==='none'?'无需登录':requirement==='account'?'需要账号':requirement==='subscription_or_provider'?'需要订阅或电视服务商':'登录 / 付费待核实'));
    if(profile==='B'){
      if(item.learning_level&&item.learning_level!=='unknown')tags.append(badge(item.learning_level));
      if(item.learning_type&&item.learning_type!=='unknown')tags.append(badge(item.learning_type));
      if(item.accent&&item.accent!=='unknown')tags.append(badge(item.accent+' 口音'));
      if(item.recommended_listening)tags.append(badge('推荐精听'));
      if(item.transcript_url)tags.append(badge(item.transcript_scope==='sample_episode'?'有示例单集文字稿':'有官方文字稿'));
      if(item.subtitles&&item.subtitles!=='unknown')tags.append(badge('字幕 '+item.subtitles));
      if(item.duration)tags.append(badge(item.duration));
    }
    if(item.type==='live_video'||item.type==='live_audio'){
      tags.append(badge(item.verification_status==='PASS'?'ffprobe 播放通过 · '+item.verification_region:'播放状态 '+(item.verification_status||'未检测')));
    }else if(item.type==='vod')tags.append(badge('视频播放未实测'));
    if(item.link_check_status==='PASS'&&item.type!=='live_video'&&item.type!=='live_audio')tags.append(badge('官方入口可达'));
    else if(item.link_check_status==='SKIPPED_POLICY')tags.append(badge('按官网政策未自动检测'));
    else if(item.link_check_status&&item.link_check_status!=='NOT_CHECKED'&&item.type!=='live_video'&&item.type!=='live_audio')tags.append(badge('入口 '+item.link_check_status));
    card.append(tags);
    const actions=make('div','','actions');
    if((item.type==='live_audio'||item.type==='live_video')&&item.verification_status==='PASS'&&item.stream_url){
      actions.append(link(item.type==='live_audio'?'收听直播':'播放直播',item.stream_url,'primary'));
    }else if(item.type==='vod')actions.append(link('打开官方视频',item.official_url,'primary'));
    else if(item.type==='live_video')actions.append(link('打开官方直播',item.official_url,'primary'));
    else if(item.type==='podcast')actions.append(link('收听 Podcast（官网）',item.official_url,'primary'));
    else if(item.learning_type&&item.learning_type!=='unknown')actions.append(link('打开课程 / 节目',item.official_url,'primary'));
    else actions.append(link('打开官方入口',item.official_url,'primary'));
    if(item.type==='podcast'&&item.rss_url&&item.link_check_status==='PASS')actions.append(link('订阅官方 RSS',item.rss_url,'secondary'));
    if(profile==='B'&&item.transcript_url)actions.append(link(item.transcript_scope==='sample_episode'?'查看示例文字稿':'查看官方文字稿',item.transcript_url,'secondary'));
    card.append(actions);cards.append(card);
  }
  $('count').textContent=`${found.length} 项内容 · ${profile==='A'?'综合精品电视':'英语学习'}`;
  $('empty').hidden=found.length!==0;
}
for(const button of document.querySelectorAll('[data-profile]'))button.addEventListener('click',()=>{
  profile=button.dataset.profile;
  for(const tab of document.querySelectorAll('[data-profile]'))tab.setAttribute('aria-pressed',String(tab===button));
  refreshFilters();
});
for(const id of ['search','type','source','category','level','learning-type'])$(id).addEventListener(id==='search'?'input':'change',render);
fetch('catalog.json').then(response=>{if(!response.ok)throw Error(response.status);return response.json()})
  .then(data=>{catalog=data;refreshFilters()})
  .catch(()=>{$('count').textContent='目录加载失败，请稍后刷新。'});
