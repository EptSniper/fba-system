#!/usr/bin/env python3
import json, re, os
BASE="/sessions/loving-dazzling-davinci/mnt/outputs"

def has(t, *pats):
    return any(re.search(p, t, re.I) for p in pats)

def snip(t, p):
    m=re.search(p, t, re.I)
    if not m: return "(not found)"
    s=max(0,m.start()-25); e=min(len(t),m.end()+25)
    return "…"+t[s:e].replace("\n"," ").strip()+"…"

def grade(skill, eid, t):
    r=[]
    def add(name, ok, ev): r.append({"text":name,"passed":bool(ok),"evidence":ev})
    if skill=="compliance":
        if eid==0:
            add("Flags Nike as gated / needs brand approval", has(t,r"gat(ed|ing)",r"brand approval",r"ungat"), snip(t,r"gat|approval|ungat"))
            add("Flags IP / authenticity / invoice risk", has(t,r"\bIP\b",r"authentic",r"invoice",r"counterfeit"), snip(t,r"invoice|authentic|\bIP\b"))
            add("Recommends list-before-buy / Seller Central check", has(t,r"seller central",r"list.{0,15}before",r"before.{0,15}buy"), snip(t,r"seller central|before"))
            add("Eligibility verdict is BLOCKED / don't buy (not a green light)", has(t,r"blocked",r"don.t (grab|buy)",r"\bpass\b",r"walk away",r"not as your plan"), snip(t,r"blocked|don.t|walk away|pass"))
        elif eid==1:
            add("Identifies hazmat (flammable/aerosol/alcohol)", has(t,r"hazmat",r"flammab",r"aerosol",r"alcohol"), snip(t,r"hazmat|flammab|alcohol"))
            add("Flags meltable/seasonal OR FBA hazmat program/restriction", has(t,r"meltab",r"seasonal",r"hazmat program",r"restrict"), snip(t,r"meltab|seasonal|restrict"))
            add("Returns VERIFY / eligibility-must-be-checked (not unqualified yes)", has(t,r"verify",r"check",r"approval",r"not.{0,10}guarantee",r"seller central"), snip(t,r"verify|check|approval"))
            add("Addresses FBA eligibility/restrictions specifically", has(t,r"\bFBA\b",r"eligib",r"restrict"), snip(t,r"FBA|eligib|restrict"))
        else:
            add("Friendly/ungated treated as a HINT, not a guarantee", has(t,r"hint",r"not.{0,15}guarantee",r"account-specific",r"not.{0,10}proof",r"doesn.t mean"), snip(t,r"hint|guarantee|account-specific|proof"))
            add("Gives decisive Seller Central / Boxem / approval check", has(t,r"seller central",r"boxem",r"approval",r"list.{0,15}before"), snip(t,r"seller central|boxem|approval"))
            add("Leans ALLOWED but with verification (not blocked)", has(t,r"allowed",r"likely.{0,15}ungat",r"auto-ungat",r"approvable",r"verify"), snip(t,r"allowed|ungat|approvable|verify"))
            add("Stays on eligibility (no ROI/profit verdict)", not has(t,r"\bROI\b",r"profit/unit",r"\bmargin\b"), "no ROI/profit verdict" if not has(t,r"\bROI\b") else snip(t,r"ROI|profit|margin"))
    else: # keepa
        if eid==0:
            add("Identifies rising offer count as avoid/negative", has(t,r"rising",r"climb",r"pil(e|ing)",r"avoid",r"more sellers",r"8.{0,5}(to|->|→).{0,5}22",r"went.{0,6}up"), snip(t,r"rising|avoid|climb"))
            add("Connects rising offers to falling/tanking price", has(t,r"tank",r"race to the bottom",r"price.{0,20}(drop|fall|slid|down)",r"undercut"), snip(t,r"tank|race|undercut|slid"))
            add("Verdict leans reject/caution on history", has(t,r"avoid",r"pass",r"reject",r"caution",r"walk",r"stay away",r"not.{0,8}buy"), snip(t,r"avoid|pass|reject|caution"))
            add("Hands off / verify / not a final buy", has(t,r"deal-analyst",r"verify",r"confirm",r"not a buy",r"selleramp"), snip(t,r"deal-analyst|verify|confirm"))
        elif eid==1:
            add("Reads demand as strong (~300/mo, BSR drops)", has(t,r"300",r"strong",r"good velocity",r"sells often"), snip(t,r"300|strong|velocity"))
            add("Notes stable price + flat offers as positive", has(t,r"stable",r"flat",r"steady"), snip(t,r"stable|flat|steady"))
            add("Notes no Amazon on listing as positive", has(t,r"no amazon",r"amazon.{0,15}(absent|not)",r"without amazon"), snip(t,r"amazon"))
            add("Verdict supports a buy on history (with verify/handoff)", has(t,r"support",r"buyable",r"healthy",r"green light",r"worth"), snip(t,r"support|buyable|healthy"))
        else:
            add("Flags Amazon ~60% Buy Box as reject/major risk", has(t,r"amazon.{0,30}(buy box|60)",r"60%",r"amazon.{0,15}(dominat|present|wins)"), snip(t,r"60%|amazon"))
            add("References ~20% threshold OR hard-reject for Amazon BB", has(t,r"20\s*%",r"hard[- ]reject",r"hard reject",r"no-go",r"reject"), snip(t,r"20\s*%|hard.reject|no-go|reject"))
            add("Reads 40->2 crash as cliff / IP / supply signal", has(t,r"cliff",r"\bIP\b",r"dried up",r"sold through",r"gating",r"40.{0,5}(to|->|→).{0,5}2"), snip(t,r"cliff|IP|dried|gating"))
            add("Verdict leans reject / pass", has(t,r"\bpass\b",r"reject",r"avoid",r"no-go",r"be.{0,10}careful",r"yellow-to-red"), snip(t,r"pass|reject|avoid|careful"))
    return r

TIM={
 "compliance":{0:[(38491,63.664),(32921,62.203)],1:[(42704,101.409),(62139,111.742)],2:[(38176,66.068),(42478,83.682)]},
 "keepa":{0:[(35298,50.680),(30567,31.942)],1:[(37399,68.564),(32929,63.632)],2:[(40675,85.521),(33176,63.788)]},
}
PROMPTS={
 "compliance":{0:"Nike Air Force 1s from a Nike outlet — flip on Amazon?",1:"scented candles + hand sanitizer for Q4 — good to send into FBA?",2:"Crayola markers — heard Crayola is easy to ungate; am I allowed to sell them?"},
 "keepa":{0:"offers 8->22 over 90d, buy box sliding $35->$28, BSR ~15k — read?",1:"BSR ~8k toys lots of drops, '300 sold', offers steady 5, buy box flat $27, no amazon — read it",2:"Keepa BB stats: Amazon ~60% of the year, offer count dropped 40->2 — thoughts?"},
}
WS={"compliance":"fba-compliance-checker-workspace","keepa":"fba-keepa-analyst-workspace"}

for skill, ws in WS.items():
    it=os.path.join(BASE,ws,"iteration-1")
    for eid in (0,1,2):
        ed=os.path.join(it,f"eval-{eid}")
        json.dump({"eval_id":eid,"prompt":PROMPTS[skill][eid]}, open(os.path.join(ed,"eval_metadata.json"),"w"), indent=2)
        for ci,config in enumerate(("with_skill","without_skill")):
            rd=os.path.join(ed,config,"run-1")
            t=open(os.path.join(rd,"outputs","analysis.md"),encoding="utf-8").read()
            json.dump({"eval_id":eid,"prompt":PROMPTS[skill][eid]}, open(os.path.join(rd,"eval_metadata.json"),"w"), indent=2)
            exps=grade(skill,eid,t); p=sum(1 for e in exps if e["passed"]); tot=len(exps)
            json.dump({"summary":{"pass_rate":round(p/tot,4),"passed":p,"failed":tot-p,"total":tot},"expectations":exps},
                      open(os.path.join(rd,"grading.json"),"w"), indent=2)
            tok,sec=TIM[skill][eid][ci]
            json.dump({"total_tokens":tok,"total_duration_seconds":sec}, open(os.path.join(rd,"timing.json"),"w"), indent=2)
    print(f"=== {skill} ===")
    for eid in (0,1,2):
        for config in ("with_skill","without_skill"):
            g=json.load(open(os.path.join(it,f"eval-{eid}",config,"run-1","grading.json")))
            s=g["summary"]; print(f"  eval-{eid} {config:14s}: {s['passed']}/{s['total']}")
