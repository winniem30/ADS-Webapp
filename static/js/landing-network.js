(() => {
  const canvas=document.getElementById('network'),ctx=canvas?.getContext('2d');if(!ctx)return;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w=0,h=0,dpr=1,nodes=[],frame=0;
  function resize(){dpr=Math.min(devicePixelRatio||1,2);w=innerWidth;h=innerHeight;canvas.width=w*dpr;canvas.height=h*dpr;canvas.style.width=`${w}px`;canvas.style.height=`${h}px`;ctx.setTransform(dpr,0,0,dpr,0,0);const count=Math.min(110,Math.max(38,Math.floor(w*h/14500)));nodes=Array.from({length:count},()=>({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-.5)*.17,vy:(Math.random()-.5)*.17,r:Math.random()*1.2+.5,phase:Math.random()*6.28}))}
  function draw(){ctx.clearRect(0,0,w,h);for(let i=0;i<nodes.length;i++){const p=nodes[i];if(!reduced){p.x+=p.vx;p.y+=p.vy;if(p.x<0||p.x>w)p.vx*=-1;if(p.y<0||p.y>h)p.vy*=-1;p.phase+=.008}for(let j=i+1;j<nodes.length;j++){const q=nodes[j],dx=p.x-q.x,dy=p.y-q.y,dist=Math.hypot(dx,dy);if(dist<145){ctx.strokeStyle=`rgba(83,191,211,${(1-dist/145)*.12})`;ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(q.x,q.y);ctx.stroke()}}const glow=.42+Math.sin(p.phase)*.18;ctx.fillStyle=`rgba(116,220,235,${glow})`;ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fill()}if(!reduced)frame=requestAnimationFrame(draw)}
  addEventListener('resize',resize,{passive:true});document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelAnimationFrame(frame);else if(!reduced)draw()});resize();draw();
})();
