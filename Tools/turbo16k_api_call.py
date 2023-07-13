# -*- coding:utf-8 -*-
import os.path
import sys
import time
import openai
import numpy as np
import argparse
import re
import tiktoken
import json
from glob import glob
from tqdm import tqdm
from datasets import load_dataset
from jsonl_utils import read_jsonl

def num_tokens_from_string(string: str, encoding_name: str) -> int:
    encoding = tiktoken.encoding_for_model(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens




def main():
    # openai.api_base = "https://api.openai-sb.com/v1"
    start_idx = 0
    for file_name in key_data_pairs:
        fw = open(f'{file_name}', "w")
        data = key_data_pairs[file_name]
        if 'gsm' in file_name:
            args.gsm = True

        if args.gsm:
            prompt = f"You are an AI visual assistant. Given several question answer pairs, you need to follow a similar format to answer the last question. Make sure the response is end with The answer is _ ."
        elif "exam" not in args.metric:
            prompt = "You are an AI visual assistant. Now you are given a very long document. Please follow the instruction after this document. These instructions may include summarizing a document, answering questions based on the document, or writing a required paragraph."
        else:
            prompt = "You are an AI visual assistant. Now you are given a very long document. Please follow the instruction based on this document. For multi-choice questions, there could be a sinlge correct option or multiple correct options. Please only provide the letter corresponding to the answer (like A or AB) when answering. For other questions, please directly give the concise and accurate answer."

        avg_pred_len = []
        for d in data:
            if d['evaluation'] == 'human' or d['evaluation'] == 'LLM':
                continue
            for inst, out in zip(d['instructions'], d['outputs']):
                avg_pred_len.append(len(out.split()))
        print('avg pred len', np.mean(avg_pred_len))

        for d in tqdm(data):
            document = d['input']
            cnt = 0
            while num_tokens_from_string(document, "gpt-3.5-turbo") > 15000:
                document = " ".join(document.split()[:11000-cnt]) # chunk the input len into 16k tokens
                cnt += 500
            
            print('document len', num_tokens_from_string(document, "gpt-3.5-turbo"))

            instructions = d['instructions']
            outputs = d['outputs']
            i = 0

            for inst, out in zip(instructions, outputs):
                messages = [{"role": "system", "content" : prompt}]
                save_d = {}
                save_d['query'] = inst
                save_d['gt'] = out
                if args.gsm:
                    messages.append({"role": "user", "content": inst})
                    save_d['prompt'] = prompt
                elif args.metric == "ngram_eval":
                    context = "Document is as follows. {} Instruction: {} " + f"The suggested output length is around {len(out.split())} words. Output: "
                    messages.append({"role": "user", "content": context.format(document, inst)})
                    save_d['prompt'] = prompt + context
                else:
                    context = "Document is as follows. {} Instruction: {} Output: "
                    messages.append({"role": "user", "content": context.format(document, inst)})
                    save_d['prompt'] = prompt + context

                for _ in range(5):
                    try:
                        if start_idx == 0:
                            print(messages[1]["content"])
                            print("--------------------------- end of example input ------------------")
                            input("Press Enter to confirm this is the correct input for the api call ...")
                            start_idx += 1
                        response = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo-16k-0613",
                            messages=messages, 
                            max_tokens=1024,
                            temperature=0.0001,
                        )  # get response
                        ret = response['choices'][0]['message']['content']
                        ret = ret.strip()  # get the paraphrased answer

                        save_d[f'{openai_model}_pred'] = ret
                        save_d['evaluation'] = d['evaluation']
                        print("----------------- [output] vs [ground truth] -----------------")
                        print('[output]:', save_d[f'{openai_model}_pred'], "\n\n" , '[ground truth]:', save_d['gt'])

                        fw.write(json.dumps(save_d) + '\n')
                        break

                    except Exception as e:  # add some logit here for retry
                        if isinstance(e, KeyboardInterrupt):
                            raise e
                        print(i, e)

                        time.sleep(0.8)
                time.sleep(1.0)
                i += 1
                # break
        fw.close()
        # break

def to_filename(task_name):
    return  os.path.join(data_save_path, task_name + ".pred.jsonl")

if __name__ == "__main__":
    openai.api_key = ""

    datasets_Exam = ["coursera", "quality", "topic_retrieval_longchat", "tpo", "gsm100"]
    datasets_Gen = ["financial_qa", "gov_report_summ", "legal_contract_qa", "meeting_summ", "multidoc_qa", "narrative_qa", "natural_question", "news_summ", "paper_assistant", "patent_summ", "review_summ", "scientific_qa", "tv_show_summ"]

    parser = argparse.ArgumentParser()
    parser.add_argument('--metric', choices=["llm_turbo_eval","llm_gpt4_eval","exam_eval", "ngram_eval", "human_eval"], default="exam_eval", help='metric name from ["turbo_eval","gpt4_eval","auto_eval", ...]')
    parser.add_argument('--task_path', type=str, default=None, help='set this if you want test a specific task , example: LEval-data/Exam/coursera.jsonl or LEval-data/Exam/ ')
    parser.add_argument('--task_name', type=str, default=None, help='set this if you want test a specific task from huggingface, example: coursera')
    parser.add_argument('--gsm', action='store_true', help='set this if you want to test gsm100 dataset')
    args = parser.parse_args()
    key_data_pairs = {}

    if args.task_name in datasets_Exam:
        args.metric = "exam_eval"
    else:
        args.metric = "ngram_eval"

    openai_model = "turbo-16k-0613"
    data_save_path = f"Predictions/{args.metric}/{openai_model}"
    os.makedirs(f"Predictions/{args.metric}", exist_ok=True)
    if "llm" not in args.metric:
        os.makedirs(data_save_path, exist_ok=True)

        if args.task_name:
            data = load_dataset('L4NLP/LEval', args.task_name, split='test')
            key_data_pairs[to_filename(args.task_name)] = data
        elif args.task_path:
            files = glob(args.task_path)
            for file_path in files:
                data = read_jsonl(file_path)
                match = re.search(r'/([^/]*)\.jsonl', file_path)
                file_name = match.group(1)
                key_data_pairs[to_filename(file_name)] = data
        else:
            if args.metric == "ngram_eval":
                datasets_eval = datasets_Gen
            else:
                datasets_eval = datasets_Exam
            for task_name in datasets_eval:
                data = load_dataset('L4NLP/LEval', task_name, split='test')
                key_data_pairs[to_filename(task_name)] = data
    else:
        for gen_data in datasets_Gen:
            try:
                data = load_dataset('L4NLP/LEval', gen_data, split='test')
            except:
                print(f"dataset {gen_data} not found in huggingface, try to load from local file")
                data = read_jsonl(f"LEval-data/Generation/{gen_data}.jsonl")
            if args.metric == "llm_turbo_eval":
                data =  [d for d in data if d["evaluation"] == "human" or d["evaluation"] == "LLM"]
            elif args.metric == "llm_gpt4_eval":
                data = [d for d in data if d["evaluation"] == "LLM"]
            else:
                data = [d for d in data if d["evaluation"] == "human"]
            file_name_llm = data_save_path + ".pred.jsonl"
            if file_name_llm not in key_data_pairs:
                key_data_pairs[file_name_llm] = data
            else:
                key_data_pairs[file_name_llm] += data

    sys.exit(main())