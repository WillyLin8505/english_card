export default function CardWorkspace({ route, target, native }: { route: string; target: string; native: string }) {
  const inspection = route.startsWith('/card-data');
  const query = new URLSearchParams(route.split('?')[1] || '');
  if (!query.has('target')) query.set('target', target);
  if (!query.has('native')) query.set('native', native);
  const url = `http://127.0.0.1:8772/${inspection ? 'admin.html' : ''}?${query}`;
  return <section style={{height:'100vh',display:'flex',flexDirection:'column'}}>
    <div style={{padding:'10px 20px',fontSize:12}}>
      {inspection ? '資料完整性、來源授權與問題標記' : '字卡結果與模板編排'}
      {' · '}<a href={url} target="_blank" rel="noreferrer">在新分頁開啟</a>
    </div>
    <iframe key={url} src={url} title={inspection ? '字卡資料檢查' : '字卡工作室'} style={{border:0,width:'100%',flex:1,minHeight:700}} />
  </section>;
}
