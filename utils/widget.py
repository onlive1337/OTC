import time
from typing import Dict, Iterable

import ujson

from config.config import ALL_CURRENCIES, CRYPTO_CURRENCIES
from config.languages import LANGUAGES

# Self-contained Telegram HTML Widget (QuickJS sandbox, <= 32KB raw / <= 4KB zlib-9).
# Strict profile rules: no <input>/<select>/<textarea>, no vh, no logical CSS properties,
# no :focus/:has(), no CSS nesting, synchronous copyText/request inside click handlers.
WIDGET_HTML = """<style>
*{box-sizing:border-box}
body{margin:0;padding:8px 12px calc(10px + env(safe-area-inset-bottom)) 12px;font-family:system-ui,sans-serif;font-size:14px;color:var(--tg-theme-text-color)}
.hd{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;gap:6px}
.tt{font-weight:700;font-size:14px;color:var(--tg-theme-accent-text-color)}
.st{font-size:11px;color:var(--tg-theme-hint-color);margin-left:auto}
.rf{padding:4px 8px;border-radius:8px;border:1px solid var(--tg-theme-section-separator-color);background:var(--tg-theme-secondary-bg-color);color:var(--tg-theme-text-color);font-size:12px}
.pills{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:6px}
.pl{padding:4px 8px;border-radius:10px;border:1px solid var(--tg-theme-section-separator-color);background:var(--tg-theme-secondary-bg-color);color:var(--tg-theme-text-color);font-size:12px;font-weight:600}
.pl.on{background:var(--tg-theme-button-color);color:var(--tg-theme-button-text-color);border-color:var(--tg-theme-button-color)}
.rd{display:flex;align-items:baseline;justify-content:space-between;padding:8px 10px;border-radius:10px;background:var(--tg-theme-secondary-bg-color);margin-bottom:6px}
.amt{font-family:monospace;font-size:20px;font-weight:700;user-select:text;-webkit-user-select:text;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cur{font-size:12px;font-weight:600;color:var(--tg-theme-hint-color);margin-left:6px}
.res{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:6px}
.rc{display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-radius:8px;background:var(--tg-theme-secondary-bg-color);border:1px solid var(--tg-theme-section-separator-color);color:var(--tg-theme-text-color);font-size:12px;text-align:left}
.rk{font-weight:600;color:var(--tg-theme-hint-color)}
.rv{font-family:monospace;font-weight:700;user-select:text;-webkit-user-select:text}
.pad{display:grid;grid-template-columns:repeat(4,1fr);gap:4px}
.k{padding:7px 4px;border-radius:8px;border:none;background:var(--tg-theme-secondary-bg-color);color:var(--tg-theme-text-color);font-size:14px;font-weight:600}
.k.ac{color:var(--tg-theme-destructive-text-color)}
.k.fn{color:var(--tg-theme-accent-text-color)}
</style>
<div class="hd"><span class="tt" id="tt">OTC</span><span class="st" id="st"></span><button class="rf" id="rf">&#x21BB;</button></div>
<div class="pills" id="pl"></div>
<div class="rd"><span class="amt" id="am">100</span><span class="cur" id="bc">USD</span></div>
<div class="res" id="rs"></div>
<div class="pad" id="pd"></div>
<script>
(function(){
var W=window.TelegramWidget;
var st={r:{USD:1,EUR:0.9,RUB:90},o:["USD","EUR","RUB"],f:"USD",a:"100",l:"ru",t:0};
var msg="";
var KEYS=["7","8","9","<","4","5","6","C","1","2","3","K","0","00",".","H"];
function parse(raw){
 if(!raw)return null;
 try{var d=JSON.parse(raw);if(d&&d.r)return d;}catch(e){}
 return null;
}
function apply(d){
 if(!d||!d.r)return;
 if(d.t&&st.t&&d.t<st.t)return;
 st.r=d.r;
 if(d.o&&d.o.length)st.o=d.o;
 if(d.l)st.l=d.l;
 if(d.t)st.t=d.t;
 if(!st.r[st.f])st.f=d.f&&st.r[d.f]?d.f:st.o[0];
}
function loadInit(){
 if(W){apply(parse(W.publicData));apply(parse(W.chatData));}
 try{
  var s=localStorage.getItem("otc_w");
  if(s){var p=JSON.parse(s);if(p.a)st.a=String(p.a);if(p.f&&st.r[p.f])st.f=p.f;}
 }catch(e){}
}
function save(){
 try{localStorage.setItem("otc_w",JSON.stringify({a:st.a,f:st.f}));}catch(e){}
}
function fmt(v,c){
 if(!isFinite(v))return"0";
 var cry={BTC:1,ETH:1,USDT:1,BNB:1,XRP:1,ADA:1,SOL:1,DOT:1,DOGE:1,TON:1,LTC:1}[c];
 if(cry){
  if(v<0.0001)return v.toPrecision(3);
  if(v<1)return Number(v.toFixed(6)).toString();
  if(v<1000)return Number(v.toFixed(4)).toString();
 }
 if(v>=1000000)return(v/1000000).toFixed(2)+"M";
 if(v<0.01&&v>0)return Number(v.toFixed(4)).toString();
 return v.toLocaleString(undefined,{maximumFractionDigits:2});
}
function rawCopy(v){
 if(!isFinite(v))return"0";
 return Number(v.toPrecision(8)).toString();
}
function render(){
 document.getElementById("tt").textContent=st.l==="ru"?"OTC Калькулятор":"OTC Calculator";
 document.getElementById("st").textContent=msg;
 document.getElementById("am").textContent=st.a||"0";
 document.getElementById("bc").textContent=st.f;
 var pl=document.getElementById("pl");
 pl.innerHTML="";
 st.o.slice(0,6).forEach(function(c){
  var b=document.createElement("button");
  b.className="pl"+(c===st.f?" on":"");
  b.textContent=c;
  b.dataset.c=c;
  pl.appendChild(b);
 });
 var rs=document.getElementById("rs");
 rs.innerHTML="";
 var num=parseFloat(st.a)||0;
 var rf=st.r[st.f]||1;
 var list=st.o.filter(function(c){return c!==st.f;}).slice(0,6);
 list.forEach(function(c){
  var val=num/rf*(st.r[c]||0);
  var b=document.createElement("button");
  b.className="rc";
  b.dataset.v=rawCopy(val);
  b.innerHTML="<span class=rk>"+c+"</span><span class=rv>"+fmt(val,c)+"</span>";
  rs.appendChild(b);
 });
}
function buildPad(){
 var pd=document.getElementById("pd");
 pd.innerHTML="";
 KEYS.forEach(function(k){
  var b=document.createElement("button");
  var lb=k==="<"?"&#x232B;":(k==="K"?"1K":(k==="H"?"100":k));
  b.className="k"+(k==="C"||k==="<"?" ac":(k==="K"||k==="H"?" fn":""));
  b.innerHTML=lb;
  b.dataset.k=k;
  pd.appendChild(b);
 });
}
document.getElementById("pl").addEventListener("click",function(e){
 var b=e.target.closest("button");if(!b)return;
 st.f=b.dataset.c;save();
 if(W&&W.HapticFeedback)W.HapticFeedback.selectionChanged();
 render();
});
document.getElementById("rs").addEventListener("click",function(e){
 var b=e.target.closest("button");if(!b)return;
 if(W&&W.copyText)W.copyText(b.dataset.v);
 if(W&&W.HapticFeedback)W.HapticFeedback.impactOccurred("light");
 msg=st.l==="ru"?"Скопировано":"Copied";
 render();
});
document.getElementById("pd").addEventListener("click",function(e){
 var b=e.target.closest("button");if(!b)return;
 var k=b.dataset.k;msg="";
 if(k==="C")st.a="0";
 else if(k==="<")st.a=st.a.length>1?st.a.slice(0,-1):"0";
 else if(k==="K")st.a=String((parseFloat(st.a)||1)*1000).slice(0,12);
 else if(k==="H")st.a="100";
 else if(k==="."){if(st.a.indexOf(".")<0)st.a+=".";}
 else{if(st.a==="0"&&k!==".")st.a=k==="00"?"0":k;else if(st.a.length<12)st.a+=k;}
 save();
 if(W&&W.HapticFeedback)W.HapticFeedback.selectionChanged();
 render();
});
document.getElementById("rf").addEventListener("click",function(){
 if(!W||!W.request)return;
 msg=st.l==="ru"?"Обновляю...":"Updating...";render();
 W.request("refresh").then(function(ans){
  if(ans&&ans.result){apply(parse(ans.result));msg=st.l==="ru"?"Обновлено":"Updated";}
  else{msg=st.l==="ru"?"Готово":"OK";}
  render();
 },function(err){
  msg=err&&err.code?err.code:"ERR";render();
 });
});
loadInit();buildPad();render();
if(W){
 W.onEvent("chatDataChanged",function(){apply(parse(W.chatData));render();});
 W.onEvent("publicDataChanged",function(){apply(parse(W.publicData));render();});
 W.ready();
}
})();
</script>"""


def _compact_rate(value: float) -> float:
    return float(f"{value:.6g}")


def build_widget_state(
    rates: Dict[str, float],
    selected_currencies: Iterable[str],
    selected_crypto: Iterable[str],
    lang: str,
    default_from: str = "USD",
    default_amount: str = "100",
) -> str:
    """Build compact JSON widget state strictly within Telegram's 1024-byte UTF-8 cap."""
    ordered: list[str] = []
    for code in [default_from, "USD", "EUR", "RUB", *selected_currencies, *selected_crypto]:
        if code in ALL_CURRENCIES and (code == "USD" or code in rates) and code not in ordered:
            ordered.append(code)
        if len(ordered) >= 7:
            break

    if not ordered:
        ordered = ["USD"]

    base = default_from if default_from in ordered else ordered[0]
    norm_lang = "ru" if lang == "ru" else "en"
    ts = int(time.time())

    while ordered:
        compact_rates = {
            c: (1 if c == "USD" else _compact_rate(rates[c]))
            for c in ordered
            if c == "USD" or c in rates
        }
        payload = ujson.dumps(
            {
                "r": compact_rates,
                "o": ordered,
                "f": base if base in ordered else ordered[0],
                "a": str(default_amount),
                "l": norm_lang,
                "t": ts,
            }
        )
        if len(payload.encode("utf-8")) <= 1024 or len(ordered) <= 1:
            return payload
        ordered.pop()

    return ujson.dumps({"r": {"USD": 1}, "o": ["USD"], "f": "USD", "a": "100", "l": norm_lang, "t": ts})


def build_widget_caption(user_lang: str) -> str:
    return LANGUAGES.get(user_lang, LANGUAGES["en"]).get(
        "widget_caption",
        "🧮 Interactive OTC currency converter",
    )


def widget_crypto_codes() -> tuple[str, ...]:
    return tuple(CRYPTO_CURRENCIES)
