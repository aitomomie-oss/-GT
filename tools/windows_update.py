"""Windows GUI updater using only Python's standard library.

Never overwrites the selected app. Snapshots SQLite and prepares a sibling release.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime
import json
import os
import shutil
import sqlite3
from contextlib import closing
import subprocess
import tempfile
import urllib.request
import zipfile

RELEASE_URL='https://github.com/aitomomie-oss/-GT/archive/refs/heads/main.zip'
MAX_ZIP=50*1024*1024
MAX_EXPANDED=200*1024*1024


def backup_database(source,destination):
    """SQLite online backup includes committed WAL data; no raw DB file copy."""
    source=Path(source);destination=Path(destination)
    if not source.is_file() or destination.exists(): raise ValueError('データファイルがないか、保存先が既に存在します。')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True,timeout=10)) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('データベースの整合性を確認できません。更新を中止します。')
        target=sqlite3.connect(destination)
        try:
            db.backup(target)
            if target.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise ValueError('バックアップ検証に失敗しました。')
        finally: target.close()


def extract_release(archive,destination):
    """Reject traversal, symlinks, credentials and bundled local data."""
    destination=Path(destination)
    if destination.exists(): raise ValueError('展開先が既にあります。')
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist()
        if len(entries)>10000 or sum(i.file_size for i in entries)>MAX_EXPANDED: raise ValueError('ZIPが大きすぎます。')
        paths=[]
        for item in entries:
            # Windows zipfile can normalize backslashes before filename is read.
            # Inspect the original archive name before trusting that normalization.
            raw_name=item.orig_filename
            p=PurePosixPath(raw_name)
            if p.is_absolute() or '..' in p.parts or '\\' in raw_name or ':' in raw_name or '\x00' in raw_name or ((item.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('安全に展開できないZIPです。')
            if not p.parts: continue
            paths.append((item,p))
        roots={p.parts[0] for _,p in paths}
        if len(roots)!=1: raise ValueError('GitHubからダウンロードしたZIPを選んでください。')
        root=next(iter(roots))
        required={f'{root}/app.py',f'{root}/requirements.txt',f'{root}/src/db/session.py'}
        if not required.issubset({i.filename for i,_ in paths}): raise ValueError('MY AI ASSETのZIPを確認できません。')
        for _,p in paths:
            relative=p.parts[1:]
            if any(v in ('local_data','data','.venv','.git') for v in relative) or (relative and relative[-1] in ('secrets.toml','.env')):
                raise ValueError('実データや認証設定を含むZIPは使用できません。')
        destination.mkdir()
        for item,p in paths:
            if len(p.parts)==1: continue
            target=destination.joinpath(*p.parts[1:])
            if item.is_dir(): target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(item) as src,target.open('xb') as out: shutil.copyfileobj(src,out)


def install_dependencies(release,runner=subprocess.run):
    # Do not inherit a custom DB binding into a new release or let pip write its credentials to a log.
    env=os.environ.copy();env.pop('MY_AI_ASSET_DB',None)
    commands=[['py','-3.12','-m','venv',str(release/'.venv')],
        [str(release/'.venv/Scripts/python.exe'),'-m','pip','install','-r',str(release/'requirements.txt')],
        [str(release/'.venv/Scripts/python.exe'),'-m','pip','check']]
    for command in commands:
        result=runner(command,cwd=str(release),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if result.returncode: raise RuntimeError('Python 3.12の確認、またはライブラリのインストールに失敗しました。元のアプリはそのまま使えます。ネット接続とPythonを確認して再実行してください。')


def prepare_release(old,archive,source_db,install=install_dependencies):
    old=Path(old).resolve()
    if not (old/'app.py').is_file(): raise ValueError('app.pyがある元のアプリフォルダを選んでください。')
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backup=old.parent/('MY_AI_ASSET_backup_'+stamp)
    release=old.parent/('MY_AI_ASSET_'+stamp)
    backup.mkdir()
    # This recovery folder persists even when download extraction or installation fails.
    if source_db:
        backup_database(source_db,backup/'assets.db')
    secret=old/'.streamlit/secrets.toml'
    if secret.is_file():
        (backup/'.streamlit').mkdir()
        shutil.copy2(secret,backup/'.streamlit/secrets.toml')
    manifest=dict(original_folder=str(old),original_database=str(source_db) if source_db else None,
        new_folder=str(release),created_at=datetime.now().astimezone().isoformat(),state='preparing')
    (backup/'update.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        extract_release(archive,release)
        if source_db:
            (release/'local_data').mkdir(exist_ok=True)
            shutil.copy2(backup/'assets.db',release/'local_data/assets.db')
        if secret.is_file():
            (release/'.streamlit').mkdir(exist_ok=True)
            shutil.copy2(backup/'.streamlit/secrets.toml',release/'.streamlit/secrets.toml')
        launcher='@echo off\nsetlocal\ncd /d "%~dp0"\nset "MY_AI_ASSET_DB="\n"%~dp0.venv\\Scripts\\python.exe" -m streamlit run app.py --server.address 127.0.0.1\npause\n'
        (release/'起動.bat').write_bytes(launcher.replace('\n','\r\n').encode('ascii'))
        install(release)
        # First launch is explicit. Migrations are deferred to the app's existing backed-up path.
        manifest['state']='ready'
        (release/'更新元.txt').write_text('旧アプリ: '+str(old)+'\nバックアップ: '+str(backup)+'\n',encoding='utf-8')
    except Exception:
        manifest['state']='failed'
        raise
    finally:
        (backup/'update.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return release,backup


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        from urllib.parse import urlparse
        p=urlparse(newurl)
        if p.scheme!='https' or p.hostname not in ('github.com','codeload.github.com') or p.username or p.password:
            raise ValueError('ダウンロード先を検証できません。')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_release(target):
    request=urllib.request.Request(RELEASE_URL,headers={'User-Agent':'MY-AI-ASSET-Updater/1.0'})
    with urllib.request.build_opener(SafeRedirect()).open(request,timeout=30) as response,open(target,'xb') as out:
        total=0
        while True:
            chunk=response.read(1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>MAX_ZIP: raise ValueError('ダウンロードサイズを超えました。')
            out.write(chunk)


def main():
    import tkinter as tk
    from tkinter import filedialog,messagebox,ttk
    root=tk.Tk();root.withdraw()
    messagebox.showinfo('MY AI ASSET 自動更新','元のアプリを残したまま、バックアップと更新版を作成します。\n\n最初に、今まで使っていたアプリのフォルダを選んでください。\napp.pyが入っているフォルダです。',parent=root)
    folder=filedialog.askdirectory(title='今まで使っていたアプリのフォルダを選択',parent=root)
    if not folder: return
    old=Path(folder)
    if not (old/'app.py').is_file(): messagebox.showerror('フォルダを確認','app.pyがあるフォルダを選び直してください。',parent=root);return
    if not messagebox.askokcancel('アプリを停止してください','アプリ起動時の黒い画面でCtrl+Cを押して停止してください。\n\n停止できたら「OK」を押してください。',parent=root): return
    candidates=[p for p in (old/'local_data/assets.db',old/'data/assets.db') if p.is_file()]
    custom=os.environ.get('MY_AI_ASSET_DB')
    if custom or len(candidates)>1:
        selected=filedialog.askopenfilename(title='実際に使用している資産データベースを選択（不明ならキャンセル）',initialdir=str(old),filetypes=[('SQLite','*.db *.sqlite *.sqlite3'),('すべて','*')],parent=root)
        if not selected: return
        db=Path(selected)
    elif candidates: db=candidates[0]
    else:
        if not messagebox.askyesno('データが見つかりません','このフォルダに標準の資産データがありません。\n\nまだ一度も資産を登録していない新規利用ですか？\n登録済みなら「いいえ」で中止してください。',parent=root): return
        db=None
    status=tk.Toplevel(root);status.title('MY AI ASSET 更新中');status.geometry('480x150')
    label=ttk.Label(status,text='最新版を取得しています。しばらくお待ちください。');label.pack(pady=25)
    bar=ttk.Progressbar(status,mode='indeterminate');bar.pack(fill='x',padx=20);bar.start()
    # A worker keeps the window responsive. All Tk interaction stays on the main thread.
    import threading,queue
    result=queue.Queue()
    with tempfile.TemporaryDirectory(prefix='my-ai-asset-update-') as temp:
        archive=Path(temp)/'release.zip'
        def download_worker():
            try: download_release(archive);result.put(('downloaded',archive))
            except Exception: result.put(('download_failed',None))
        def install_worker(path):
            try: result.put(('ready',prepare_release(old,path,db)))
            except Exception: result.put(('error',None))
        completed=tk.BooleanVar(value=False)
        status.protocol('WM_DELETE_WINDOW',lambda:messagebox.showinfo('更新中','処理が終わるまでこの画面を閉じずにお待ちください。',parent=status))
        def poll():
            try: kind,value=result.get_nowait()
            except queue.Empty: root.after(150,poll);return
            if kind=='download_failed':
                chosen=filedialog.askopenfilename(title='ブラウザーでダウンロードした最新版の -GT-main.zip を選択',filetypes=[('GitHub ZIP','*.zip')],parent=status)
                if not chosen: status.destroy();completed.set(True);return
                value=Path(chosen);kind='downloaded'
            if kind=='downloaded':
                label.config(text='バックアップ・更新版の準備中です。数分かかることがあります。')
                threading.Thread(target=install_worker,args=(value,),daemon=True).start();root.after(150,poll);return
            status.destroy()
            if kind=='ready':
                release,backup=value
                os.startfile(str(release))
                messagebox.showinfo('更新版の準備ができました','開いた新しいフォルダの「起動.bat」をダブルクリックしてください。\n起動後、今までの資産が表示されるか確認してください。\n\nバックアップ:\n'+str(backup)+'\n\nこれからは新しいフォルダを使ってください。古いアプリも残っています。',parent=root)
            else:
                messagebox.showerror('更新を完了できませんでした','元のアプリと元のデータは変更していません。\n元のフォルダの隣に作成されたバックアップは残してください。\n\nPython 3.12・インターネット接続・空き容量を確認してください。\n「MY_AI_ASSET_数字」の未完成フォルダからは起動しないでください。',parent=root)
            completed.set(True)
        threading.Thread(target=download_worker,daemon=True).start();root.after(150,poll)
        root.wait_variable(completed)
    root.destroy()


if __name__=='__main__': main()
