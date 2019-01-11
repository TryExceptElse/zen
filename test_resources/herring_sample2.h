#include <vector>
#include <string>

namespace sample {

/**
 * Sample class declaration
 */
class Foo {
 public:
  explicit Foo(/*test*/std::vector<int> numbers): numbers_(numbers) {}

  void Print() const;
 private:
  std::vector<int> numbers_;
};

/**
 * Irrelevant, unused class declaration
 */
class RedHerring {
 public:
  explicit RedHerring() {}

  std::string get_shrubbery() const { return "Not another shrubbery"; }
};


static RedHerring herring;

}  // namespace sample
