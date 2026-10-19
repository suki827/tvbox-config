const labels={live_video:'电视直播',live_audio:'广播直播',vod:'官方点播',podcast:'Podcast',official_link:'官方入口'};
const el=id=>document.getElementById(id);
let catalog={sources:[],items:[]},profile='A';
function node(tag,text,className){const e=document.createElement(tag);e.textContent=text;if(className)e.className=className;return e}
function tag(text){return node('span',text,'tag')}
function render(){
 const sources=Object.fromEntries(catalog.sources.map(s=>[s.id,s]));
 const q=el('search').value.trim().toLocaleLowerCase(),type=el('type').value,category=el('category').value;
 const found=catalog.items.filter(i=>i.profiles.includes(profile)&& (type==='all'||i.type===type) && (category==='all'||sources[i.source_id].categories.includes(category)) && (!q||[i.title,i.description,sources[i.source_id].name,...sources[i.source_id].categories].join(' ').toLocaleLowerCase().includes(q)));
 const cards=el('cards');cards.replaceChildren();
 for(const item of found){const src=sources[item.source_id],card=node('article','','card');
 card.append(node('div',src.name,'source'),node('h2',item.title));
 if(item.description)card.append(node('p',item.description));
 const tags=node('div','','tags');tags.append(tag(labels[item.type]||item.type),tag(src.country),tag(src.nz_access||'NZ_UNVERIFIED'));
 if(src.availability_regions==='NZ')tags.append(tag('仅限新西兰服务'));else if(src.availability_regions==='US')tags.append(tag('美国权益限制'));else if(src.availability_regions==='international_live')tags.append(tag('官网国际直播'));
 if(src.access_requirements!=='unknown')tags.append(tag(src.access_requirements==='none'?'无需登录':src.access_requirements==='account'?'需要账号':src.access_requirements==='subscription_or_provider'?'需要订阅或电视服务商':src.access_requirements));
 else tags.append(tag('登录 / 付费待核实'));
 if(profile==='B'){if(item.learning_level!=='unknown')tags.append(tag(item.learning_level));if(item.accent!=='unknown')tags.append(tag(item.accent));if(item.recommended_listening)tags.append(tag('推荐精听'));if(item.transcript_url)tags.append(tag('有官方文字稿'));if(item.subtitles!== 'unknown')tags.append(tag('字幕 '+item.subtitles));if(item.duration)tags.append(tag(item.duration))}
 if(item.link_check_status==='PASS')tags.append(tag('官网入口检测通过'));else if(item.link_check_status==='SKIPPED_POLICY')tags.append(tag('按官网政策未自动检测'));else if(item.link_check_status&&item.link_check_status!=='NOT_CHECKED')tags.append(tag('入口检测: '+item.link_check_status));
 card.append(tags);
 if(profile==='B'&&item.transcript_url){const transcript=node('a','官方文字稿');transcript.href=item.transcript_url;transcript.target='_blank';transcript.rel='noopener noreferrer';card.append(transcript)}
 const link=node('a','打开官方入口');link.href=item.official_url;link.target='_blank';link.rel='noopener noreferrer';card.append(link);cards.append(card)}
 el('count').textContent=`${found.length} 项内容 · ${profile==='A'?'综合精品电视':'英语学习'}`;el('empty').hidden=found.length>0;
}
function categories(){const sources=Object.fromEntries(catalog.sources.map(s=>[s.id,s]));const values=new Set(catalog.items.filter(i=>i.profiles.includes(profile)).flatMap(i=>sources[i.source_id].categories));const select=el('category');select.replaceChildren(new Option('全部分类','all'),...[...values].sort().map(v=>new Option(v,v)));render()}
for(const button of document.querySelectorAll('[data-profile]'))button.addEventListener('click',()=>{profile=button.dataset.profile;for(const b of document.querySelectorAll('[data-profile]'))b.setAttribute('aria-pressed',String(b===button));categories()});
for(const id of ['search','type','category'])el(id).addEventListener(id==='search'?'input':'change',render);
fetch('catalog.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(data=>{catalog=data;categories()}).catch(()=>{el('count').textContent='目录加载失败，请稍后刷新。'});
