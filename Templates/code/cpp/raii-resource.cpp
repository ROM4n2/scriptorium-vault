#pragma once
#include <iostream>
#include <memory>
#include <string>
#include <utility>

// ==============================================================================
// 📦 Modern C++ RAII Resource Wrapper (C++20 Rule of Five Pattern)
// ==============================================================================

class SafeResource {
private:
    int* handle_{nullptr};
    std::string name_;

public:
    explicit SafeResource(std::string name)
        : handle_(new int(42)), name_(std::move(name)) {
        std::cout << "[RAII] Acquired: " << name_ << "\n";
    }

    ~SafeResource() noexcept {
        if (handle_) {
            std::cout << "[RAII] Released: " << name_ << "\n";
            delete handle_;
            handle_ = nullptr;
        }
    }

    // Disable copy to enforce unique ownership
    SafeResource(const SafeResource&) = delete;
    SafeResource& operator=(const SafeResource&) = delete;

    // Enable noexcept move semantics
    SafeResource(SafeResource&& other) noexcept
        : handle_(std::exchange(other.handle_, nullptr)),
          name_(std::move(other.name_)) {}

    SafeResource& operator=(SafeResource&& other) noexcept {
        if (this != &other) {
            delete handle_;
            handle_ = std::exchange(other.handle_, nullptr);
            name_ = std::move(other.name_);
        }
        return *this;
    }

    [[nodiscard]] const std::string& name() const noexcept { return name_; }
    [[nodiscard]] bool is_valid() const noexcept { return handle_ != nullptr; }
};
