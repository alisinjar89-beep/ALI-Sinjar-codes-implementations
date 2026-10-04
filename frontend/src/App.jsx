import React, {useMemo, useState} from 'react';

const endpoint = import.meta.env.VITE_RASA_WEBHOOK || 'http://localhost:5005/webhooks/rest/webhook';
const initial = [{
  from: 'bot',
  text: 'Hello. Eco-Travel Advisor compares lower-carbon travel choices, prices, and responsible local experiences.',
  buttons: [
    {title: 'Plan a trip', payload: '/plan_trip'},
    {title: 'Compare carbon', payload: '/ask_carbon'}
  ]
}];

function bandClass(band){ return ['green','amber','red'].includes(band) ? band : 'amber'; }

// دالة تحديد لون شريط التقدم بناءً على قيمة Eco Score
function getEcoProgressColor(score) {
  const num = Number(score) || 0;
  if (num >= 75) return '#2e7d32'; // أخضر
  if (num >= 50) return '#81c784'; // أخضر فاتح
  if (num >= 30) return '#ffb74d'; // برتقالي
  return '#e53935'; // أحمر
}

function App(){
  const [messages,setMessages] = useState(initial);
  const [input,setInput] = useState('');
  const [handover,setHandover] = useState(false);
  const [busy,setBusy] = useState(false);
  const [locationStatus,setLocationStatus] = useState('Location optional');
  const sender = useMemo(() => `web-${Math.random().toString(36).slice(2,9)}`, []);

  async function send(value){
    const text = (value || input).trim();
    if(!text || busy) return;
    setMessages(m => [...m,{from:'user',text}]);
    setInput('');
    setBusy(true);
    try{
      const response = await fetch(endpoint,{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({sender,message:text})
      });
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const next = [];
      for(const item of data){
        if(item.text) next.push({from:'bot',text:item.text,buttons:item.buttons||[]});
        const custom = item.custom || {};
        if(custom.eco_options){
          next.push({
            from:'bot',
            cards:custom.eco_options.transport||[],
            hotels:custom.eco_options.hotels||[],
            note:custom.eco_options.source_note
          });
        }
        if(custom.carbon_result) next.push({from:'bot',carbon:custom.carbon_result});
        if(custom.handover?.active){
          setHandover(true);
          next.push({from:'bot',text:custom.handover.display||'Human advisor handover active'});
        }
      }
      setMessages(m => [...m,...(next.length?next:[{from:'bot',text:'No response payload was returned.'}])]);
    }catch(error){
      setMessages(m => [...m,{from:'bot',text:'The Rasa endpoint is currently unavailable. Start Docker Compose, then retry.'}]);
    }finally{
      setBusy(false);
    }
  }

  function shareLocation(){
    if(!navigator.geolocation){
      setLocationStatus('Browser location unavailable');
      return;
    }
    setLocationStatus('Requesting permission');
    navigator.geolocation.getCurrentPosition(
      position => {
        const lat = position.coords.latitude.toFixed(5);
        const lon = position.coords.longitude.toFixed(5);
        setLocationStatus('Location shared for this chat');
        send(`/inform_location{"origin_lat":${lat},"origin_lon":${lon},"location_consent":true}`);
      },
      () => setLocationStatus('Location permission declined'),
      {enableHighAccuracy:false,timeout:5000,maximumAge:300000}
    );
  }

  return <main className="shell">
    <header>
      <div className="brand"><span className="leaf">●</span><b>Eco-Travel Advisor</b><small>Responsible choices, transparent evidence</small></div>
      <div className="headerActions">
        <button className="location" onClick={shareLocation} aria-label="Share current location">Use my location</button>
        <span className="status">Rasa REST</span>
      </div>
    </header>
    <div className="locationNote" role="status">{locationStatus}. Manual departure cities remain supported.</div>
    {handover && <div className="handover">Human advisor handover active. Conversation context is packaged securely.</div>}
    <section className="chat" aria-live="polite">
      {messages.map((message,index) => <div key={index} className={`msg ${message.from}`}>
        <div className="bubble">
          {message.text && <p>{message.text}</p>}
          {message.note && <p className="note">{message.note}</p>}
          {message.carbon && <div className="carbon">
            <b>Carbon estimate</b>
            <span>{message.carbon.verified_live ? `${message.carbon.kg_co2e} kgCO2e` : 'Live value unavailable'}</span>
            <small>{message.carbon.source}</small>
          </div>}
          {message.cards && <><h4>Transport comparison</h4><div className="cards">
            {message.cards.slice(0,3).map((item,j) => {
              const score = item.eco_score ?? 0;
              return (
                <article className={`card ${bandClass(item.emission_band)}`} key={j}>
                  <div className="tag">{item.emission_band?.toUpperCase()}</div>
                  <h3>{item.name}</h3>
                  <p>{item.carbon_kg ?? 'Unverified'} kgCO2e · {item.price ?? 'Price unavailable'} {item.currency}</p>
                  <strong>Eco score {score}/100</strong>
                  <div style={{width: '100%', backgroundColor: '#e0e0e0', borderRadius: '6px', height: '8px', marginTop: '6px', overflow: 'hidden'}}>
                    <div style={{width: `${Math.min(Math.max(score, 0), 100)}%`, backgroundColor: getEcoProgressColor(score), height: '100%', borderRadius: '6px', transition: 'width 0.4s ease'}} />
                  </div>
                </article>
              );
            })}
          </div></>}
          {message.hotels && <><h4>Accommodation carousel</h4><div className="cards horizontal" role="region" aria-label="Eco accommodation options">
            {message.hotels.slice(0,4).map((item,j) => {
              const score = item.eco_score ?? 0;
              return (
                <article className={`card ${bandClass(item.emission_band)}`} key={j}>
                  <div className="tag">{item.verification_status?.includes('unverified') ? 'VERIFY CLAIM' : 'ECO OPTION'}</div>
                  <h3>{item.name}</h3>
                  <p>{item.price ?? 'Price unavailable'} {item.currency}</p>
                  <strong>Eco score {score}/100</strong>
                  <div style={{width: '100%', backgroundColor: '#e0e0e0', borderRadius: '6px', height: '8px', marginTop: '6px', overflow: 'hidden'}}>
                    <div style={{width: `${Math.min(Math.max(score, 0), 100)}%`, backgroundColor: getEcoProgressColor(score), height: '100%', borderRadius: '6px', transition: 'width 0.4s ease'}} />
                  </div>
                </article>
              );
            })}
          </div></>}
          {message.buttons?.length>0 && <div className="buttons">
            {message.buttons.map((button,j) => <button key={j} onClick={() => send(button.payload)}>{button.title}</button>)}
          </div>}
        </div>
      </div>)}
    </section>
    <footer>
      <input aria-label="Message" value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&send()} placeholder="Describe a trip or ask about carbon..."/>
      <button onClick={()=>send()} disabled={busy}>{busy?'...':'Send'}</button>
    </footer>
  </main>;
}

export default App;
