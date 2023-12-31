from tqdm import tqdm
import logging
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    BertTokenizer,
    AlbertForMaskedLM,
    DataCollatorForLanguageModeling,
    AdamW,
    get_cosine_schedule_with_warmup,
    TrainingArguments,
)


# set device
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

# load model and tokenizer
tokenizer = BertTokenizer.from_pretrained("voidful/albert_chinese_base")
new_vocab_file = "/content/drive/MyDrive/BERT-NER-dev/data/new_vocab.txt"
tokenizer.add_tokens(new_vocab_file, special_tokens=True)
model = AlbertForMaskedLM.from_pretrained("voidful/albert_chinese_base").to(device)
model.resize_token_embeddings(len(tokenizer))

# load dataset
class TextDataset(Dataset):
    def __init__(self, tokenizer, file_path, block_size):
        self.examples = []
        with open(file_path, encoding="utf-8") as f:
            text = f.read()
        tokenized_text = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(text))
        for i in range(0, len(tokenized_text) - block_size + 1, block_size):
            self.examples.append(
                tokenizer.build_inputs_with_special_tokens(tokenized_text[i : i + block_size])
            )

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, i):
        return torch.tensor(self.examples[i])

block_size = 128
num_train_epochs = 8
per_device_train_batch_size = 8
learning_rate = 5e-6
warmup_steps = 1000
mlm_probability = 0.1
dropout_rate = 0.3
weight_decay = 0.01
gradient_accumulation_steps = 4
learning_rate_scheduler = 'cosine'

dataset = TextDataset(
    tokenizer=tokenizer,
    file_path="/content/drive/MyDrive/BERT-NER-dev/data/combined.txt",
    block_size=block_size,
)

# create data collator for Mask Language Modelling
data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer, mlm=True, mlm_probability=mlm_probability
)

# training arguments for pretraining
training_args = TrainingArguments(
    output_dir="./aec_albert",
    overwrite_output_dir=True,
    num_train_epochs=num_train_epochs,
    per_device_train_batch_size=per_device_train_batch_size,
    gradient_accumulation_steps=gradient_accumulation_steps,
    weight_decay=weight_decay,
    learning_rate=learning_rate,
    adam_epsilon=1e-8,
    warmup_steps=warmup_steps,
    logging_dir="./logs",
    logging_steps=500,
    save_total_limit=1,
    save_steps=500,
    # learning_rate_scheduler=None, # disable default scheduler
)

# optimizer and scheduler
optimizer = AdamW(model.parameters(), lr=learning_rate, correct_bias=False, weight_decay=weight_decay)
scheduler = get_cosine_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=len(dataset) * num_train_epochs, num_cycles=0.5)

# # set up logger
# logger = SimpleLogger()

## train loop
model.train()
for epoch in range(num_train_epochs):
    total_loss = 0
    data_loader = DataLoader(dataset, batch_size=training_args.per_device_train_batch_size)
    for step, inputs in enumerate(tqdm(data_loader)):
        inputs = inputs.to(device)
        outputs = model(inputs, labels=inputs)
        loss = outputs.loss
        total_loss += loss.item()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
        scheduler.step()
    print(f"Epoch {epoch + 1} - loss: {total_loss / len(dataset)}")

## save model to disk once training is done
model.save_pretrained("./aec_albert-uncased")
tokenizer.save_pretrained("./aec_albert-uncased")
