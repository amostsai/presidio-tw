"""CLI demo using the same configuration and reversible tokens as the Web app."""
import argparse
import os
from pathlib import Path
from pii_service import DEFAULT_CONFIG, load_config, create_service, PiiTransform
from pii_service.recognizers import validate_tw_id, validate_tw_tax_id
from restoration import MappingSession

DEMO = ('學創科技的工程師林宗漢在台北市信義區上班，'
        '他的聯絡手機是 0912-345-678，身分證字號是 A123456789，'
        '公司統一編號為 80112345，請盡速聯繫。')


def main():
    parser = argparse.ArgumentParser(description='設定式台灣個資辨識與可復原脫敏')
    parser.add_argument('--config', type=Path, default=os.environ.get('PII_CONFIG', DEFAULT_CONFIG))
    parser.add_argument('--text', default=DEMO)
    parser.add_argument('--no-ner', action='store_true', help='本次停用 CKIP，僅使用設定中的規則')
    parser.add_argument('--mapping', type=Path, help='明確指定時才寫入含完整個資的還原 JSON')
    args = parser.parse_args()
    try:
        cfg = load_config(args.config)
        if args.no_ner: cfg['ner']['enabled'] = False
        service = create_service(cfg)
        session = MappingSession('text.txt')
        masked = PiiTransform(service, session)(args.text)
        print('--- 脫敏後文本 ---')
        print(masked)
        print('--- 辨識統計 ---')
        for entity,count in session.report()['entities'].items(): print(f'{entity}: {count}')
        if args.mapping:
            args.mapping.write_bytes(session.dump())
            print(f'還原檔：{args.mapping}（包含真實資料，請留在本機）')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'錯誤：{exc}\n')


if __name__ == '__main__': main()
