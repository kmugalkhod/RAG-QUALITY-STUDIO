import { describe, expect, it, vi } from 'vitest';
import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
const loader = readFileSync('public/v1.0.0/loader.js', 'utf8');
const id = '11111111-2222-3333-4444-555555555555';
function host(tokenUrl='/api/rag-widget/token') {
  const dom = new JSDOM('<!doctype html><body></body>', {url:'http://127.0.0.1:5275/',runScripts:'outside-only'});
  const { window } = dom;
  const script = window.document.createElement('script');
  script.src='http://127.0.0.1:5274/v1.0.0/loader.js';
  script.dataset.rqsDeploymentId=id;
  if (tokenUrl !== null) script.dataset.rqsTokenUrl=tokenUrl;
  window.document.body.append(script);
  Object.defineProperty(window.document,'currentScript',{configurable:true,get:()=>script});
  window.matchMedia=()=>({matches:false});
  window.fetch=vi.fn();
  return window;
}
describe('public loader',()=>{
  it('inserts one isolated frame across repeated root-layout scripts',()=>{
    const window=host();
    window.eval(loader); window.eval(loader);
    expect(window.document.querySelectorAll('iframe')).toHaveLength(1);
    expect(window.document.querySelector('iframe').src).toBe(`http://127.0.0.1:5274/v1.0.0/frame/${id}`);
    expect(window.document.body.innerHTML).not.toMatch(/rqs_live_|rqs_widget_/);
  });
  it('loads a public one-script embed without a customer token route',()=>{
    const window=host(null); window.eval(loader);
    expect(window.document.querySelector('iframe')).not.toBeNull();
    const frame=window.document.querySelector('iframe');
    frame.contentWindow.postMessage=vi.fn();
    frame.dispatchEvent(new window.Event('load'));
    const init=frame.contentWindow.postMessage.mock.calls[0][0];
    window.dispatchEvent(new window.MessageEvent('message',{source:frame.contentWindow,origin:'http://127.0.0.1:5274',data:{...init,type:'token-needed'}}));
    expect(window.fetch).not.toHaveBeenCalled();
    window.close();
  });
  it('rejects a cross-origin customer token URL and a copied message',()=>{
    const invalid=host('https://evil.test/token'); invalid.eval(loader);
    expect(invalid.document.querySelector('iframe')).toBeNull();
    const window=host(); window.eval(loader);
    const frame=window.document.querySelector('iframe');
    frame.contentWindow.postMessage=vi.fn();
    frame.dispatchEvent(new window.Event('load'));
    const init=frame.contentWindow.postMessage.mock.calls[0][0];
    window.dispatchEvent(new window.MessageEvent('message',{source:frame.contentWindow,origin:'http://127.0.0.1:5276',data:{...init,type:'token-needed'}}));
    expect(window.fetch).not.toHaveBeenCalled();
    window.close();
  });
  it('requests a token only from the first-party backend after a checked handshake',async()=>{
    const window=host(); window.eval(loader);
    const frame=window.document.querySelector('iframe');
    frame.contentWindow.postMessage=vi.fn();
    frame.dispatchEvent(new window.Event('load'));
    const init=frame.contentWindow.postMessage.mock.calls[0][0];
    window.fetch.mockResolvedValue({ok:false,status:401});
    window.dispatchEvent(new window.MessageEvent('message',{source:frame.contentWindow,origin:'http://127.0.0.1:5274',data:{...init,type:'token-needed'}}));
    await Promise.resolve();
    expect(window.fetch).toHaveBeenCalledWith('/api/rag-widget/token',expect.objectContaining({method:'POST',credentials:'same-origin',redirect:'error'}));
    window.close();
  });
  it('ignores forged frame messages with a wrong source, nonce or protocol version',()=>{
    const window=host(); window.eval(loader);
    const frame=window.document.querySelector('iframe');
    frame.contentWindow.postMessage=vi.fn();
    frame.dispatchEvent(new window.Event('load'));
    const init=frame.contentWindow.postMessage.mock.calls[0][0];
    const forged=[
      {source:window,origin:'http://127.0.0.1:5274',data:{...init,type:'token-needed'}},
      {source:frame.contentWindow,origin:'http://127.0.0.1:5274',data:{...init,nonce:'0'.repeat(32),type:'token-needed'}},
      {source:frame.contentWindow,origin:'http://127.0.0.1:5274',data:{...init,version:'0.0.0',type:'token-needed'}},
    ];
    forged.forEach(message=>window.dispatchEvent(new window.MessageEvent('message',message)));
    expect(window.fetch).not.toHaveBeenCalled();
    window.close();
  });
  it('waits for the body when loaded from a shared head layout',()=>{
    const window=host();
    window.document.body.remove();
    window.eval(loader);
    expect(window.document.querySelector('iframe')).toBeNull();
    window.document.documentElement.appendChild(window.document.createElement('body'));
    window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
    expect(window.document.body.querySelectorAll('iframe')).toHaveLength(1);
    window.close();
  });
  it('rejects a missing deployment ID',()=>{
    const window=host();
    window.document.currentScript.dataset.rqsDeploymentId='';
    window.eval(loader);
    expect(window.document.querySelector('iframe')).toBeNull();
    window.close();
  });
});
