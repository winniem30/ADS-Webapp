const config=window.ADS_FIREBASE_CONFIG||{};
const validFirebaseConfig=Boolean(config.apiKey&&config.authDomain&&config.projectId&&config.appId);
let firebaseAuth=null,firebaseModules=null;
async function firebase(){
  if(firebaseAuth)return {auth:firebaseAuth,...firebaseModules};
  const [appSdk,authSdk]=await Promise.all([
    import('https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js'),
    import('https://www.gstatic.com/firebasejs/12.19.0/firebase-auth.js')
  ]);
  const app=appSdk.initializeApp(config);
  firebaseAuth=authSdk.getAuth(app);firebaseModules=authSdk;
  return {auth:firebaseAuth,...firebaseModules};
}
const errorBox=document.getElementById('auth-error'),loading=document.getElementById('auth-loading');
function showError(message){if(errorBox)errorBox.textContent=message}
function setBusy(value){if(loading)loading.hidden=!value;document.querySelectorAll('.auth-submit').forEach(b=>b.disabled=value)}

document.getElementById('dev-signin')?.addEventListener('click',async()=>{
  setBusy(true);showError('');
  try{const r=await fetch('/auth/dev-session',{method:'POST',credentials:'same-origin',headers:{Accept:'application/json'}});const d=await r.json();if(!r.ok)throw new Error(d.error||'Local sign-in failed.');location.assign(window.ADS_NEXT||'/dashboard')}
  catch(e){showError(e.message);setBusy(false)}
});

document.getElementById('firebase-signin')?.addEventListener('submit',async event=>{
  event.preventDefault();showError('');setBusy(true);
  try{
    if(!validFirebaseConfig)throw new Error('Firebase web configuration is incomplete. Ask the project administrator to configure the required environment variables.');
    const {auth,signInWithEmailAndPassword}=await firebase();
    const form=new FormData(event.currentTarget);
    const credential=await signInWithEmailAndPassword(auth,form.get('email'),form.get('password'));
    const idToken=await credential.user.getIdToken(true);
    const response=await fetch('/auth/session',{method:'POST',credentials:'same-origin',headers:{Authorization:`Bearer ${idToken}`,Accept:'application/json'}});
    const body=await response.json();if(!response.ok)throw new Error(body.error||'Could not establish a secure session.');
    location.assign(window.ADS_NEXT||'/dashboard');
  }catch(e){showError(e.message||'Sign-in failed. Check your details and try again.');setBusy(false)}
});

document.getElementById('signout')?.addEventListener('click',async()=>{
  const button=document.getElementById('signout');button.disabled=true;
  try{
    if(window.ADS_AUTH_MODE==='firebase'&&validFirebaseConfig){const {auth,signOut}=await firebase();await signOut(auth)}
    await fetch('/auth/session/logout',{method:'POST',credentials:'same-origin',headers:{Accept:'application/json'}});
  }finally{location.assign('/')}
});
