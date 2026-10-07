(() => {
  document.querySelector('#print-button')?.addEventListener('click',()=>window.print());
  const sidebar=document.querySelector('#sidebar'), backdrop=document.querySelector('#sidebar-backdrop');
  document.querySelector('#menu-toggle')?.addEventListener('click',()=>{sidebar.classList.toggle('open');backdrop.classList.toggle('open')});
  backdrop?.addEventListener('click',()=>{sidebar.classList.remove('open');backdrop.classList.remove('open')});
  document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();document.querySelector('.global-search input')?.focus()}if(e.key==='Escape'){sidebar?.classList.remove('open');backdrop?.classList.remove('open')}});
  document.querySelectorAll('form[data-confirm]').forEach(form=>form.addEventListener('submit',e=>{if(!confirm(form.dataset.confirm))e.preventDefault()}));
  document.querySelector('#add-item')?.addEventListener('click',()=>{const count=document.querySelector('#id_items-TOTAL_FORMS'), n=Number(count.value);document.querySelector('#items-container').insertAdjacentHTML('beforeend',document.querySelector('#empty-item').innerHTML.replaceAll('__prefix__',n));count.value=n+1});
  let dragged=null, pending=null;
  const status=document.querySelector('#kanban-status');
  async function move(card,column,reason=''){
    const csrf=document.querySelector('[name=csrfmiddlewaretoken]').value;
    const data=new URLSearchParams({stage:column.dataset.stage,reason});
    try{
      const response=await fetch(`/leads/${card.dataset.id}/stage/`,{method:'POST',headers:{'X-CSRFToken':csrf,'Accept':'application/json'},body:data});
      const result=await response.json();
      if(!response.ok||!result.ok)throw new Error(result.error||'Não foi possível alterar a etapa.');
      const old=card.closest('.kanban-column');column.querySelector('.kanban-empty')?.remove();column.querySelector('.kanban-dropzone').append(card);
      [old,column].forEach(col=>col.querySelector('.count-badge').textContent=col.querySelectorAll('.lead-card').length);
      status.textContent='Etapa atualizada.';
    }catch(error){alert(error.message);status.textContent=error.message}
  }
  document.querySelectorAll('.lead-card').forEach(card=>{card.addEventListener('dragstart',e=>{dragged=card;card.classList.add('dragging');e.dataTransfer.setData('text/plain',card.dataset.id)});card.addEventListener('dragend',()=>{card.classList.remove('dragging');document.querySelectorAll('.dragover').forEach(col=>col.classList.remove('dragover'))})});
  document.querySelectorAll('.kanban-column').forEach(column=>{column.addEventListener('dragover',e=>{e.preventDefault();column.classList.add('dragover')});column.addEventListener('dragleave',e=>{if(!column.contains(e.relatedTarget))column.classList.remove('dragover')});column.addEventListener('drop',e=>{e.preventDefault();column.classList.remove('dragover');if(!dragged||dragged.closest('.kanban-column')===column)return;if(column.dataset.kind==='lost'){pending={card:dragged,column};document.querySelector('#loss-dialog').showModal()}else move(dragged,column)})});
  document.querySelector('#loss-form')?.addEventListener('submit',e=>{e.preventDefault();move(pending.card,pending.column,document.querySelector('#loss-reason').value);document.querySelector('#loss-dialog').close();pending=null});
  document.querySelector('#cancel-loss')?.addEventListener('click',()=>{document.querySelector('#loss-dialog').close();pending=null});
})();
