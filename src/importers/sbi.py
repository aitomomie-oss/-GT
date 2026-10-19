"""User-confirmed column mapping, never a claimed fixed native SBI format."""
from src.importers.trades import read_csv, preview_rows, REQUIRED, TRADE_FIELDS


class SBIImporter:
    def preview(self,content,mapping,defaults=None,value_maps=None,header_row=0,delimiter=',',date_format='%Y-%m-%d'):
        headers,records=read_csv(content,header_row,delimiter)
        defaults=defaults or {}
        value_maps=value_maps or {}
        if not isinstance(value_maps,dict) or any(not isinstance(v,dict) for v in value_maps.values()):
            raise ValueError('値マッピングは辞書で指定してください')
        if any(column not in headers for column in mapping.values() if column):
            raise ValueError('対応付けに存在しない列が指定されています')
        for key in REQUIRED:
            if not mapping.get(key) and not str(defaults.get(key,'')).strip():
                raise ValueError(f'{key}: 列または利用者確認済みの固定値が必要です')
        rows=[]
        for record in records:
            raw={key:record[mapping[key]] if mapping.get(key) else defaults.get(key,'') for key in TRADE_FIELDS}
            for key,values in value_maps.items():
                if key in raw:
                    raw[key]=values.get(str(raw[key]).strip(),raw[key])
            rows.append(raw)
        return preview_rows(rows,'SBI証券',date_format)

    def import_bytes(self,db,content,mapping=None,**options):
        # Retains the safe failure contract tested in Phase 1.
        if mapping is None:
            raise ValueError('SBI証券固有CSVは未対応: 実際のヘッダーと列マッピングの確認が必要です')
        if not options.pop('confirmed',False):
            raise ValueError('保存前に確認プレビューが必要です')
        from src.services.imports import register_batch
        complete=options.pop('complete_history',False)
        savings=options.pop('is_savings',False)
        entries=self.preview(content,mapping,**options)
        return register_batch(db,content,'SBI CSV（利用者マッピング）',entries,{'mapping':mapping,**options},complete_history=complete,is_savings=savings,confirmed=True)
